"""Shared utilities: config loading, seeding, logging, (de)serialization.

Research environment only — not a clinical tool.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import random
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    """Load a YAML config. Falls back to JSON if the file is .json."""
    if path.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    import yaml  # pyyaml; available in the project venv
    with open(path) as f:
        return yaml.safe_load(f)


def states_path(cfg: dict) -> str:
    """Per-patient encoded-states file for the active encoder (GRU vs CLMBR)."""
    import os
    fn = "encoded_states_clmbr.pkl" if cfg["encoder"]["kind"] == "clmbr" else "encoded_states.pkl"
    return os.path.join(cfg["data"]["out_dir"], fn)


def deep_update(base: dict, overrides: dict) -> dict:
    """Recursively merge ``overrides`` into ``base`` (returns a new dict)."""
    out = dict(base)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_update(out[k], v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str = "cfa") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(asctime)s %(levelname)s %(name)s] %(message)s",
                                         datefmt="%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def save_pickle(obj: Any, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_pickle(path: str) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)


def save_json(obj: Any, path: str, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=indent, default=str)
