"""smoke_rollout_api.py — verify rollout_api loads the WM and produces well-formed rich output.

Picks the same kind of test patient rollout_counterfactual.main picks (abnormal-baseline, has actions,
enough horizon), enumerates candidate plans, rolls out, and asserts the output structure. MC sampling is
stochastic so we seed for reproducibility and check sanity, not exact parity with rollout_example.json.
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # llm_coupling/
import rollout_api as R  # noqa: E402

BASE = R.BASE


def main():
    torch.manual_seed(0)
    np.random.seed(0)
    engine = R.load_engine()
    print(f"engine loaded on {R.DEV}; zdim={engine.ck['zdim']} adim={engine.ck['adim']}")
    print(f"outcome_names in ckpt: {engine.ck.get('outcome_names')}")

    sub = pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))
    sp = json.loads((BASE / "data/splits.json").read_text())
    test = set(sp["splits"]["test"])

    chosen = None
    for e in sub:
        if int(e["patient_id"]) not in test:
            continue
        if e["s"].shape[0] >= 6 and float(np.abs(np.asarray(e["action_matrix"])[1:6]).sum()) > 0:
            chosen = e
            break
    assert chosen is not None, "no suitable test patient found"
    pid = int(chosen["patient_id"])
    print(f"chosen test patient {pid}  T={chosen['s'].shape[0]}  arm={chosen['outcomes'].get('arm')}")

    plans = R.enumerate_candidate_plans(chosen, engine.schema, horizon=5)
    print(f"enumerated {len(plans)} plans: {list(plans)}")
    for name, seq in plans.items():
        assert seq.shape[1] == engine.ck["adim"], f"{name} wrong action dim {seq.shape}"

    out = R.rollout_from_entry(engine, chosen, horizon=5, plans=plans)

    # structural assertions
    assert set(out["plans"]) == set(plans)
    for name, p in out["plans"].items():
        assert len(p["lab_trajectory"]) == out["horizon_steps"]
        assert len(p["outcome_risk_trajectory"]) == out["horizon_steps"]
        fm = p["final_mortality_risk"]
        assert set(fm) == {"mean", "lo", "hi"}
        assert 0.0 <= fm["mean"] <= 1.0, f"{name} mortality out of range: {fm}"
        assert fm["lo"] <= fm["mean"] <= fm["hi"] + 1e-6
    assert "deltas" in out["treatment_contrast"]
    assert "flag" in out["reliability"]

    print("\n--- summary ---")
    print(json.dumps({
        "patient_id": out["patient_id"], "arm": out["arm"],
        "actual_outcome": out["actual_outcome"],
        "baseline_labs": out["baseline_labs"],
        "reliability": out["reliability"]["flag"],
        "final_mortality_by_plan": {k: v["final_mortality_risk"]["mean"] for k, v in out["plans"].items()},
        "contrast": out["treatment_contrast"],
    }, indent=2))

    # dump full output so we can eyeball / diff against rollout_example.json
    outdir = BASE / "llm_coupling/tests/_out"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "smoke_rollout.json").write_text(json.dumps(out, indent=2))
    print(f"\nOK — full output -> {outdir / 'smoke_rollout.json'}")


if __name__ == "__main__":
    main()
