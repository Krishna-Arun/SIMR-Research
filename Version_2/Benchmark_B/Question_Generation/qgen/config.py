"""Config loading + path/cache resolution for the Benchmark A question-generation system.

Keeps everything on $SCRATCH (HF/torch caches included) per project policy — never $HOME, never
$OAK. A single typed accessor (`load_config`) so downstream modules don't re-parse YAML.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent          # Version_2/Question_Generation
DEFAULT_CONFIG = REPO_ROOT / "config" / "qgen.yaml"
SCRATCH = os.environ.get("SCRATCH", "/scratch/users/karun09")


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load qgen.yaml, set $SCRATCH-bound caches, and validate the essentials."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh)

    _set_scratch_caches()
    _validate(cfg)
    cfg["_config_path"] = str(cfg_path)
    return cfg


def _set_scratch_caches() -> None:
    """Force every cache that defaults to $HOME onto $SCRATCH (15 GB $HOME fills fast)."""
    caches = {
        "HF_HOME": f"{SCRATCH}/.huggingface",
        "HF_HUB_CACHE": f"{SCRATCH}/.huggingface/hub",
        "TRANSFORMERS_CACHE": f"{SCRATCH}/.huggingface/transformers",
        "TORCH_HOME": f"{SCRATCH}/.torch",
        "XDG_CACHE_HOME": f"{SCRATCH}/.cache",
        "PIP_CACHE_DIR": f"{SCRATCH}/.pip",
    }
    for k, v in caches.items():
        os.environ.setdefault(k, v)
        Path(v).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def mimic_root(cfg: dict) -> Path:
    """Resolve the active MIMIC-IV root by data.source."""
    src = cfg["data"].get("source", "full")
    key = "full_root" if src == "full" else "demo_root"
    return Path(cfg["data"][key])


def out_dir(cfg: dict) -> Path:
    d = Path(cfg["data"]["out_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate(cfg: dict) -> None:
    for key in ("data", "cohort", "time_zero", "generation", "models", "pubmed_mcp"):
        if key not in cfg:
            raise ValueError(f"qgen.yaml missing required top-level section: {key!r}")
    if not mimic_root(cfg).exists():
        raise FileNotFoundError(f"MIMIC root does not exist: {mimic_root(cfg)}")
    tz = cfg["time_zero"].get("policy")
    if tz not in ("icu_intime_plus", "first_micro", "procedure"):
        raise ValueError(f"time_zero.policy must be icu_intime_plus|first_micro|procedure, got {tz!r}")


if __name__ == "__main__":
    import json
    c = load_config()
    print(json.dumps({k: v for k, v in c.items() if not k.startswith("_")}, indent=2, default=str))
    print("mimic_root:", mimic_root(c))
