"""add_outcome_decoder.py — train the outcome-risk head z -> [mortality, mortality_30d] and fold it
into the existing world_model_enriched.pt checkpoint. Patient-level AUROC on the held-out test split
(predicted risk averaged per patient, so timepoint repetition can't inflate it)."""
import json, pickle
from pathlib import Path
import numpy as np, torch, torch.nn as nn
from sklearn.metrics import roc_auc_score
from train_substrate_wm import LABN, NL

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
DEV = "cuda" if torch.cuda.is_available() else "cpu"
OUTC = ["mortality", "mortality_30d"]


class OutcomeDecoder(nn.Module):
    def __init__(self, zdim, k):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(zdim, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, k))
    def forward(self, z): return self.net(z)          # logits


def main():
    sub = pickle.load(open(BASE/"data/train_substrate.pkl","rb"))
    sp = json.loads((BASE/"data/splits.json").read_text())
    tr_s, te_s = set(sp["splits"]["train"]), set(sp["splits"]["test"])
    ck = torch.load(BASE/"data/world_model_enriched.pt", map_location=DEV)
    zdim = ck["zdim"]

    Z, Y, PID = [], [], []
    for e in sub:
        pid = int(e["patient_id"]); o = e["outcomes"]
        y = [int(o.get(k, 0) or 0) for k in OUTC]
        for row in e["s"]:
            Z.append(row); Y.append(y); PID.append(pid)
    Z = np.asarray(Z, np.float32); Y = np.asarray(Y, np.float32); PID = np.asarray(PID)
    trm, tem = np.isin(PID, list(tr_s)), np.isin(PID, list(te_s))
    print(f"timepoints {len(Z):,}  outcome prevalence (all): " +
          ", ".join(f"{k}={Y[:,i].mean():.3f}" for i,k in enumerate(OUTC)))

    Zt = torch.tensor(Z, device=DEV); Yt = torch.tensor(Y, device=DEV)
    dec = OutcomeDecoder(zdim, len(OUTC)).to(DEV)
    opt = torch.optim.Adam(dec.parameters(), 1e-3, weight_decay=1e-4)
    tri = np.where(trm)[0]
    for ep in range(60):
        dec.train(); perm = tri[torch.randperm(len(tri)).numpy()]
        for b in range(0, len(perm), 512):
            idx = perm[b:b+512]
            loss = nn.functional.binary_cross_entropy_with_logits(dec(Zt[idx]), Yt[idx])
            opt.zero_grad(); loss.backward(); opt.step()

    dec.eval()
    with torch.no_grad():
        risk = torch.sigmoid(dec(Zt[tem])).cpu().numpy()
    # patient-level: mean predicted risk vs patient label
    te_pids = PID[tem]
    aucs = {}
    for i, k in enumerate(OUTC):
        rows = []
        for p in np.unique(te_pids):
            m = te_pids == p
            rows.append((risk[m, i].mean(), Y[tem][m, i][0]))
        r = np.array(rows)
        if len(np.unique(r[:,1])) < 2:
            aucs[k] = None; continue
        aucs[k] = round(float(roc_auc_score(r[:,1], r[:,0])), 3)
    print("patient-level test AUROC:", aucs)

    ck["outcome_dec"] = dec.state_dict(); ck["outcome_names"] = OUTC
    torch.save(ck, BASE/"data/world_model_enriched.pt")
    (BASE/"data/outcome_decoder_metrics.json").write_text(json.dumps({"test_auroc": aucs}, indent=2))
    print("saved outcome_dec into world_model_enriched.pt")


if __name__ == "__main__":
    main()
