"""Stage 2 — patient-state encoder.  s_t = encoder(x_<=t)

Two interchangeable implementations behind ``EncoderBase``:

  * GRUEncoder        — from-scratch CLMBR-style autoregressive encoder. Embeds (code, type,
                        value), runs a GRU, and is trained with a next-event prediction objective.
                        The per-step hidden states ARE the patient states s_t. Runs anywhere, no
                        external deps beyond torch. Default latent dim 256.

  * CLMBRFemrEncoder  — the official frozen CLMBR (StanfordShahLab/clmbr-t-base) loaded via femr,
                        used as a feature extractor. Emits 768-d per-event representations aligned
                        to event timestamps. Requires the femr stack + MEDS-format input + the
                        Athena OMOP vocabulary (see preprocessing/to_meds.py).

Everything downstream (world model, simulator, benchmark, RL) consumes s_t through this interface
and reads the latent dim from config, so GRU<->CLMBR is a config switch, not a rewrite.

Research environment only — not a clinical tool; no causal-validity claims.
"""
from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn

from models.featurize import EVENT_TYPES


class EncoderBase(nn.Module):
    """Common interface. ``latent_dim`` is the dimensionality of s_t."""
    latent_dim: int

    def encode(self, *args, **kwargs):
        """Return per-event states s of shape [T, latent_dim] for one patient timeline."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# GRU baseline (CLMBR-style next-event SSL)
# ---------------------------------------------------------------------------
class GRUEncoder(EncoderBase):
    def __init__(self, vocab_size: int, cfg: dict):
        super().__init__()
        g = cfg["encoder"]["gru"]
        self.embed_dim = g["embed_dim"]
        self.hidden_dim = g["hidden_dim"]
        self.latent_dim = g["hidden_dim"]
        self.code_emb = nn.Embedding(vocab_size, self.embed_dim, padding_idx=0)
        self.type_emb = nn.Embedding(len(EVENT_TYPES) + 1, 16, padding_idx=0)
        self.value_proj = nn.Linear(1, 16)
        in_dim = self.embed_dim + 16 + 16
        self.gru = nn.GRU(in_dim, self.hidden_dim, num_layers=g["num_layers"],
                          batch_first=True, dropout=(g["dropout"] if g["num_layers"] > 1 else 0.0))
        self.dropout = nn.Dropout(g["dropout"])
        # next-event prediction head (autoregressive SSL objective -> CLMBR recipe)
        self.next_code = nn.Linear(self.hidden_dim, vocab_size)

    def _embed(self, code, typ, value):
        e = self.code_emb(code)
        t = self.type_emb(typ)
        v = self.value_proj(value.unsqueeze(-1))
        return torch.cat([e, t, v], dim=-1)

    def forward(self, batch: dict):
        """Returns (hidden_states [B,T,H], next_code_logits [B,T,V])."""
        x = self._embed(batch["code"], batch["type"], batch["value"])
        h, _ = self.gru(x)
        h = self.dropout(h)
        logits = self.next_code(h)
        return h, logits

    @torch.no_grad()
    def encode(self, code, typ, value) -> torch.Tensor:
        """Encode one timeline (1D tensors) -> states [T, H]."""
        self.eval()
        device = next(self.parameters()).device
        batch = {"code": code.unsqueeze(0).to(device),
                 "type": typ.unsqueeze(0).to(device),
                 "value": value.unsqueeze(0).to(device)}
        h, _ = self.forward(batch)
        return h.squeeze(0)


# ---------------------------------------------------------------------------
# Official CLMBR (frozen) via femr
# ---------------------------------------------------------------------------
class CLMBRFemrEncoder(EncoderBase):
    """Thin frozen wrapper around StanfordShahLab/clmbr-t-base.

    Loaded lazily so the rest of the package imports without femr installed. Input patients must be
    in MEDS schema (see Stage 0 smoke + preprocessing/to_meds.py).
    """

    def __init__(self, cfg: dict):
        super().__init__()
        self.model_name = cfg["encoder"].get("clmbr_model", "StanfordShahLab/clmbr-t-base")
        self.latent_dim = cfg["encoder"].get("clmbr_dim", 768)
        self._loaded = False
        self.tokenizer = None
        self.batch_processor = None
        self.model = None

    def load(self):
        if self._loaded:
            return
        import femr.models.tokenizer
        import femr.models.processor
        import femr.models.transformer
        self.tokenizer = femr.models.tokenizer.FEMRTokenizer.from_pretrained(self.model_name)
        self.batch_processor = femr.models.processor.FEMRBatchProcessor(self.tokenizer)
        self.model = femr.models.transformer.FEMRModel.from_pretrained(self.model_name)
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad_(False)
        self._loaded = True

    @torch.no_grad()
    def encode(self, meds_patient: dict) -> dict:
        """Encode one MEDS-schema patient -> {'s': [T,768], 't': timestamps, 'patient_ids': ...}."""
        if not self._loaded:
            self.load()
        raw = self.batch_processor.convert_patient(meds_patient, tensor_type="pt")
        batch = self.batch_processor.collate([raw])
        if torch.cuda.is_available():
            self.model = self.model.cuda()
            batch = {k: (v.cuda() if torch.is_tensor(v) else v) for k, v in batch.items()}
        _, result = self.model(**batch)
        return {"s": result["representations"],
                "t": result["timestamps"],
                "patient_ids": result["patient_ids"]}


# ---------------------------------------------------------------------------
def build_encoder(cfg: dict, vocab_size: Optional[int] = None) -> EncoderBase:
    kind = cfg["encoder"]["kind"]
    if kind == "gru":
        assert vocab_size is not None, "GRU encoder needs a vocab_size"
        return GRUEncoder(vocab_size, cfg)
    if kind == "clmbr":
        return CLMBRFemrEncoder(cfg)
    raise ValueError(f"unknown encoder.kind={kind!r}")
