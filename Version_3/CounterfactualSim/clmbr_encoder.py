#!/usr/bin/env python3
"""
CLMBR encoder — patient event timeline -> sequence of state embeddings.

This is the ENCODER half of the counterfactual-simulation engine. It wraps Stanford
Shah Lab's CLMBR-t-base (a 141M autoregressive EHR foundation model over OMOP concepts),
producing one embedding per patient "state" (time-step). The V-JEPA2-style world model
(world_model.py) then rolls those embeddings forward under an intervention.

STATUS: WORKING on laptop (Apple Silicon, CPU). The real CLMBR path runs via `femr`
in the local venv `.venv_clmbr` (Python 3.11). Two modes:
  - backend='clmbr', precomputed: load per-patient embeddings produced by
    encode_cohort.py from embeddings/<subject_id>.npy  (default, fast, no femr needed).
  - backend='clmbr', live: build a MEDS patient dict from an event timeline and run the
    femr FEMRModel forward pass (requires the .venv_clmbr interpreter / femr installed).
A dependency-free FALLBACK encoder remains for environments without the real stack.

Assets already present locally:
  - CLMBR weights:  ../loaded_models/clmbr-t-base/{model.safetensors,config.json,
                    dictionary.msgpack, clmbr_v8_original_dictionary.json}
  - OMOP vocabulary: ../../vocabulary_download_v5_{...}/CONCEPT.csv  (Athena)
  - Precomputed cohort embeddings: ./embeddings/<subject_id>.npy + ./embeddings/index.json

Reproduce the embeddings (from Version_3/CounterfactualSim/):
    python3.11 -m venv .venv_clmbr && .venv_clmbr/bin/pip install \
        femr==0.2.3 transformers==4.35.2 datasets==2.15.0 torch
    # (xformers is shimmed for CPU; see build notes) then:
    .venv_clmbr/bin/python build_icd_map.py        # ICD -> OMOP-standard crosswalk
    .venv_clmbr/bin/python encode_cohort.py        # -> embeddings/*.npy + index.json
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CLMBR_DIR = REPO / "Version_3" / "loaded_models" / "clmbr-t-base"
# newest OMOP vocab download (CONCEPT.csv lives here)
_VOCAB_CANDIDATES = sorted(REPO.glob("vocabulary_download_v5_*"))
VOCAB_DIR = _VOCAB_CANDIDATES[-1] if _VOCAB_CANDIDATES else None

CLMBR_DIM = 768        # clmbr-t-base hidden size (from config.json)
EMB_DIR = REPO / "Version_3" / "CounterfactualSim" / "embeddings"
BUILD_DIR = REPO / "Version_3" / "CounterfactualSim" / "meds_build"
BIRTH_CODE = "SNOMED/184099003"


class CLMBREncoder:
    """Encode a patient's event timeline into a [T, D] float array of state embeddings.

    backend='clmbr' uses the real model (requires femr + a MEDS/OMOP timeline);
    backend='fallback' uses a deterministic hash embedding of (concept, value-bucket)
    so the engine is runnable end-to-end before the OMOP pipeline exists.
    """

    def __init__(self, backend: str | None = None, dim: int = CLMBR_DIM,
                 model_dir: Path = CLMBR_DIR, emb_dir: Path = EMB_DIR):
        self.dim = dim
        self.backend = backend or os.environ.get("SIMR_ENCODER", "fallback")
        self.model_dir = Path(model_dir)
        self.emb_dir = Path(emb_dir)
        self._model = None
        self._tok = None
        self._bp = None
        self._lab_map = None
        if self.backend == "clmbr":
            self._load_clmbr()

    # ── real CLMBR ──────────────────────────────────────────────────────────
    def _load_clmbr(self):
        """Lazily import femr and load CLMBR-t-base. If femr is unavailable, we can
        still serve precomputed embeddings (encode_patient); only live encode()
        needs the model. So a missing femr is a soft failure here."""
        try:
            import femr.models.tokenizer, femr.models.processor, femr.models.transformer  # noqa
        except Exception as e:
            self._model = None
            self._femr_error = e
            return
        self._tok = femr.models.tokenizer.FEMRTokenizer.from_pretrained(str(self.model_dir))
        self._bp = femr.models.processor.FEMRBatchProcessor(self._tok)
        m = femr.models.transformer.FEMRModel.from_pretrained(str(self.model_dir))
        m.eval()
        self._model = m
        self._femr_error = None

    # ---- precomputed path: look up a cohort patient's saved embeddings --------
    def encode_patient(self, subject_id) -> np.ndarray:
        """Return the [T, dim] CLMBR embeddings for a cohort subject_id, loading the
        .npy produced by encode_cohort.py. Raises if not precomputed."""
        p = self.emb_dir / f"{int(subject_id)}.npy"
        if not p.exists():
            raise FileNotFoundError(
                f"no precomputed CLMBR embedding for subject {subject_id} at {p}. "
                f"Run encode_cohort.py, or use encode(timeline) for a live forward pass.")
        return np.load(p).astype(np.float32)

    def encode(self, timeline: list[dict]) -> np.ndarray:
        """timeline: list of events, each {code|concept, time, value?}. Returns [T, dim]."""
        if self.backend == "clmbr":
            return self._encode_clmbr(timeline)
        return self._encode_fallback(timeline)

    def _encode_clmbr(self, timeline) -> np.ndarray:
        """Live forward pass: build a MEDS patient dict from `timeline` and run CLMBR.

        Each event may carry: 'code' (already an OMOP code-string like 'SNOMED/..'
        or 'LOINC/..'), or a MIMIC lab 'itemid' (mapped via lab_to_loinc.json), plus
        optional 'time' (datetime/ISO str) and numeric 'value'. Codes absent from the
        CLMBR vocabulary are silently dropped by the tokenizer.
        """
        import datetime as _dt
        if self._model is None:
            raise RuntimeError(
                "CLMBR femr model not loaded (femr import failed: %r). Use the .venv_clmbr "
                "interpreter, or call encode_patient(subject_id) for precomputed embeddings."
                % getattr(self, "_femr_error", None))
        if self._lab_map is None:
            import json
            f = BUILD_DIR / "lab_to_loinc.json"
            self._lab_map = ({int(k): v for k, v in json.loads(f.read_text()).items()}
                             if f.exists() else {})

        def _to_dt(t, default):
            if t is None:
                return default
            if isinstance(t, _dt.datetime):
                return t
            return __import__("pandas").Timestamp(t).to_pydatetime()

        base = _dt.datetime(2000, 1, 1)
        events = [{"time": base, "measurements": [
            {"code": BIRTH_CODE, "numeric_value": None, "text_value": None}]}]
        for i, ev in enumerate(timeline):
            code = ev.get("code") or ev.get("concept")
            if code is None and ev.get("itemid") is not None:
                code = self._lab_map.get(int(ev["itemid"]))
            if not code:
                continue
            val = ev.get("value", ev.get("valuenum"))
            try:
                nv = float(val) if val is not None else None
            except (TypeError, ValueError):
                nv = None
            t = _to_dt(ev.get("time"), base + _dt.timedelta(hours=i + 1))
            events.append({"time": t, "measurements": [
                {"code": str(code), "numeric_value": nv, "text_value": None}]})
        events.sort(key=lambda e: e["time"])
        patient = {"patient_id": 0, "events": events}
        import torch
        raw = self._bp.convert_patient(patient, tensor_type="pt")
        batch = self._bp.collate([raw])
        with torch.no_grad():
            _, res = self._model(**batch)
        reps = res["representations"].cpu().numpy().astype(np.float32)
        if reps.size == 0:
            return np.zeros((1, self.dim), dtype=np.float32)
        return reps

    # ── fallback (laptop) ───────────────────────────────────────────────────
    def _vec(self, token: str) -> np.ndarray:
        h = hashlib.sha256(token.encode()).digest()
        # expand the 32-byte hash into a dim-vector deterministically
        reps = int(np.ceil(self.dim / 32))
        raw = (h * reps)[: self.dim]
        v = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (v - 127.5) / 127.5

    def _encode_fallback(self, timeline) -> np.ndarray:
        rows = []
        for ev in timeline:
            code = str(ev.get("code") or ev.get("concept") or ev.get("lab") or "EVENT")
            val = ev.get("value", ev.get("valuenum"))
            bucket = ""
            try:
                bucket = f":b{int(float(val) // 1)}" if val is not None else ""
            except (TypeError, ValueError):
                bucket = ""
            rows.append(self._vec(code + bucket))
        if not rows:
            return np.zeros((1, self.dim), dtype=np.float32)
        return np.stack(rows)


if __name__ == "__main__":
    import json
    enc = CLMBREncoder(backend="fallback")
    tl = [{"code": "Creatinine", "value": 4.3}, {"code": "Potassium", "value": 5.1},
          {"code": "Dialysis"}]
    z = enc.encode(tl)
    print("fallback encoder OK — timeline", len(tl), "-> states", z.shape,
          "| vocab:", VOCAB_DIR.name if VOCAB_DIR else "MISSING",
          "| clmbr weights present:", (CLMBR_DIR / "model.safetensors").exists())

    # Precomputed CLMBR path (no femr import needed) — show >=3 cohort patients.
    idx_path = EMB_DIR / "index.json"
    if idx_path.exists():
        clm = CLMBREncoder.__new__(CLMBREncoder)  # skip femr load; only need file lookup
        clm.emb_dir, clm.dim = EMB_DIR, CLMBR_DIM
        idx = json.loads(idx_path.read_text())
        ok = [s for s, v in idx["patients"].items() if "path" in v]
        print(f"precomputed CLMBR embeddings available for {len(ok)} cohort patients")
        for sid in ok[:3]:
            print("  subject", sid, "-> states", clm.encode_patient(sid).shape)
    else:
        print("no precomputed embeddings yet — run encode_cohort.py")
