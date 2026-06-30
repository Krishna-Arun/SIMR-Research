"""Atomic JSONL append + resume + run manifest.

questions.jsonl is append-only (one record/line); requeues continue toward 500 without recompute.
load_resume() reconstructs used-patient/fingerprint/type-count state from what's already written.
"""
from __future__ import annotations

import json
from pathlib import Path

from qgen.schema import PIPELINE_VERSION, intent_fingerprint


class Writer:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.out_dir / "questions.jsonl"
        self.manifest_path = self.out_dir / "run_manifest.json"
        self.complete_sentinel = self.out_dir / "QGEN_COMPLETE"

    def append(self, record: dict) -> None:
        with open(self.path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def load_resume(self):
        """Return (records, used_hadm:set, fingerprints:set, type_counts:dict)."""
        records, used_hadm, fps = [], set(), set()
        type_counts = {"diagnosis": 0, "intervention": 0}
        if not self.path.exists():
            return records, used_hadm, fps, type_counts
        with open(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                records.append(rec)
                used_hadm.add(int(rec["hadm_id"]))
                fps.add(intent_fingerprint(rec))
                t = rec.get("type")
                if t in type_counts:
                    type_counts[t] += 1
        return records, used_hadm, fps, type_counts

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with open(self.path) as fh:
            return sum(1 for line in fh if line.strip())

    def write_manifest(self, cfg: dict, type_counts: dict, n: int, extra: dict | None = None) -> None:
        manifest = {
            "pipeline_version": PIPELINE_VERSION,
            "n_questions": n,
            "type_counts": type_counts,
            "seed": cfg.get("seed"),
            "data_source": cfg["data"]["source"],
            "models": {r: cfg["models"][r]["model_id"] for r in cfg["models"]},
            "time_zero": cfg["time_zero"],
            "cohort": cfg["cohort"],
            **(extra or {}),
        }
        with open(self.manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=2, default=str)

    def mark_complete(self):
        self.complete_sentinel.write_text("done\n")
