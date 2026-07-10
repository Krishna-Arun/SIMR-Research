"""Stage 2b.1 — convert MIMIC-IV to MEDS via meds_etl_mimic (Athena-independent).

meds_etl_mimic expects ``<src>/2.2/{hosp,icu}/*.csv.gz``. The demo ships as ``<root>/{hosp,icu}``,
so we stage a versioned dir of symlinks. Emits MEDS parquet (MIMIC-native codes like
``MIMIC_IV_ITEM/<itemid>``, ``ICD10CM/...``) under ``data.meds_dir``.

Run inside the clmbr311 venv:
    python preprocessing/build_meds.py configs/default.yaml
Research environment only — not a clinical tool.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.common import load_config, get_logger

log = get_logger("build_meds")
MIMIC_VERSION = "2.2"   # meds_etl 0.2.3 hardcodes this; full v3.1 schema is close — symlink under 2.2.


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml"
    cfg = load_config(cfg_path)
    src = cfg["data"]["demo_root"] if cfg["data"]["source"] == "demo" else cfg["data"]["full_root"]
    meds_dir = cfg["data"]["meds_dir"]
    stage = os.path.join(cfg["data"]["out_dir"], "mimic_src")

    os.makedirs(os.path.join(stage, MIMIC_VERSION), exist_ok=True)
    for sub in ("hosp", "icu"):
        link = os.path.join(stage, MIMIC_VERSION, sub)
        target = os.path.join(src, sub)
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link) if os.path.islink(link) else None
        if not os.path.exists(link):
            os.symlink(target, link)
    log.info("staged %s -> %s/%s", src, stage, MIMIC_VERSION)

    if os.path.exists(meds_dir):
        log.error("meds_dir %s already exists; remove it first (meds_etl_mimic needs a fresh dir).",
                  meds_dir)
        sys.exit(1)

    cmd = ["meds_etl_mimic", stage, meds_dir, "--num_shards", "4", "--num_proc", "4"]
    log.info("running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    log.info("MEDS written -> %s", meds_dir)


if __name__ == "__main__":
    main()
