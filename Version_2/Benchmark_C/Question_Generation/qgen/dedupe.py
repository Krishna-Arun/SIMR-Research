"""Seeding + cross-question de-duplication.

- Each admission (hadm_id) is used at most once -> no two questions on the same patient.
- Each intent fingerprint (type + gold lab/micro signature) is used at most once -> diversity even
  across distinct patients.
State is reconstructed on resume from the existing questions.jsonl (see writer.load_resume).
"""
from __future__ import annotations

import numpy as np

from qgen.schema import intent_fingerprint


class DedupeState:
    def __init__(self, seed: int, used_hadm: set[int] | None = None,
                 fingerprints: set[str] | None = None):
        self.rng = np.random.default_rng(seed)
        self.used_hadm = set(used_hadm or set())
        self.fingerprints = set(fingerprints or set())

    def is_dup(self, candidate: dict) -> bool:
        return intent_fingerprint(candidate) in self.fingerprints

    def register(self, hadm_id: int, candidate: dict) -> None:
        self.used_hadm.add(int(hadm_id))
        self.fingerprints.add(intent_fingerprint(candidate))

    def mark_used(self, hadm_id: int) -> None:
        """Mark a patient consumed even if its question was rejected (no re-sampling)."""
        self.used_hadm.add(int(hadm_id))
