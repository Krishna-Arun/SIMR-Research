"""Emit the `vllm serve ...` command line for a model role from qgen.yaml.

Used by jobs/serve_models.sbatch so the serving command always matches the config (model id, port,
tensor-parallel size, quantization, context length). Keeps "model sizes are TBD" entirely in YAML.

Usage:  python -m qgen.serve_cmd optimizer   ->   prints the vllm command for the optimizer role
"""
from __future__ import annotations

import sys

from qgen.config import load_config


def serve_cmd(role: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    m = cfg["models"][role]
    parts = ["vllm", "serve", m["model_id"],
             "--port", str(m["port"]),
             "--tensor-parallel-size", str(m.get("tensor_parallel_size", 1)),
             "--gpu-memory-utilization", str(m.get("gpu_memory_utilization", 0.9)),
             "--max-model-len", str(m.get("max_model_len", 16384)),
             "--served-model-name", m["model_id"]]
    if m.get("quantization"):
        parts += ["--quantization", str(m["quantization"])]
    if m.get("tool_calling") == "native":
        parts += ["--enable-auto-tool-choice", "--tool-call-parser", m.get("tool_call_parser", "hermes")]
    return " ".join(parts)


if __name__ == "__main__":
    print(serve_cmd(sys.argv[1] if len(sys.argv) > 1 else "optimizer"))
