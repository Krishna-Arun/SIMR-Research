# Version 2 — Ollama Local Setup Guide

You now have **Version 2 fully configured to run locally via Ollama on your MacBook**. No cloud APIs, no GPU requirements beyond what Ollama can do locally.

## What Changed

### New Files
- **`qgen/ollama_backend.py`** (in each benchmark A/B/C) — Ollama-compatible backend implementing the same interface as vLLM/HuggingFace backends
- **`test_ollama_connection.py`** — Quick connectivity + model availability test (run this first!)

### Updated Files
- **`qgen/hf_backend.py`** (A/B/C) — Factory function now supports `backend: ollama`
- **`config/qgen.yaml`** (A/B/C) — Now uses Ollama models:
  - `optimizer`: `qwen3.6:latest` (your 27B Qwen)
  - `evaluator`: `deepseek-r1:14b` (to be downloaded)
- **`config/qgen_pilot.yaml` & `qgen_smoke.yaml`** — Same updates for testing configs

---

## Setup Steps

### Step 1: Download the DeepSeek Model

```bash
ollama pull deepseek-r1:14b
```

This downloads the quantized 14B model (~8-9 GB). Verify both models are present:

```bash
ollama list
```

You should see:
```
qwen3.6:latest         38 GB      
deepseek-r1:14b       8 GB
```

### Step 2: Start Ollama Server

In a **separate terminal**, start Ollama:

```bash
ollama serve
```

This launches the OpenAI-compatible API on `http://localhost:11434/v1`. Leave this running while you test/benchmark.

### Step 3: Verify the Connection

Run the test script (in the main repo directory):

```bash
python3 Version_2/test_ollama_connection.py
```

Expected output:
```
🔧 OLLAMA CONNECTION TEST

============================================================
Testing Ollama endpoint connectivity...
============================================================
✓ Connected to Ollama at http://localhost:11434/v1
✓ Available models: ['qwen3.6:latest', 'deepseek-r1:14b']

============================================================
Model 1: Optimizer (Qwen 3.6 27B)
============================================================
Testing Optimizer (qwen3.6:latest)...
  ✓ Health check passed
  ✓ Chat call succeeded
    Response: test passed

============================================================
Model 2: Evaluator (DeepSeek-R1-Distill-Qwen-14B)
============================================================
Testing Evaluator (deepseek-r1:14b)...
  ✓ Health check passed
  ✓ Chat call succeeded
    Response: test passed

============================================================
SUMMARY
============================================================
✅ All tests passed! Ready to run benchmarks.
```

---

## Running Benchmarks

### Quick Smoke Test (3-10 questions)

```bash
cd Version_2/Benchmark_A/Question_Generation
python -m qgen.run_generate config/qgen_smoke.yaml --pilot
```

**Expected flow:**
1. Starts PubMed MCP server (Node.js)
2. Polls Ollama endpoints until both models are healthy
3. Builds cohort + context store
4. Generates 10 questions sequentially
5. Appends to `outputs/questions.jsonl`

### Full Run (500 questions)

```bash
cd Version_2/Benchmark_A/Question_Generation
python -m qgen.run_generate config/qgen.yaml
```

This will take hours (1–4 min per question with Ollama on MacBook). It's **resumable**: if interrupted, just run the same command again — it picks up from the last checkpoint.

### Repeat for Benchmarks B & C

Same pattern, different directories:
```bash
cd Version_2/Benchmark_B/Question_Generation
python -m qgen.run_generate config/qgen.yaml

cd Version_2/Benchmark_C/Question_Generation
python -m qgen.run_generate config/qgen.yaml
```

---

## Architecture Notes

### How Ollama Integration Works

The code uses a **pluggable backend system**:

```python
# In qgen/hf_backend.py:
def make_chat(role_cfg: dict):
    backend = role_cfg.get("backend", "vllm")
    if backend == "hf":
        return HFChat(role_cfg)
    elif backend == "ollama":
        return OllamaChat(role_cfg)  # ← new!
    return VLLMChat(role_cfg)
```

Each backend (vLLM, HuggingFace, Ollama) implements:
- `__init__(role_cfg)` — load config
- `healthy()` — health check (orchestrator polls this)
- `chat(messages, tools=None, temp=None)` → `ChatResult`

So the **agentic loop in `qgen/agentic_loop.py` doesn't care which backend is used** — it just calls `.chat()` and `.healthy()`.

### Ollama Specifics

- **Endpoint:** `http://localhost:11434/v1` (OpenAI-compatible)
- **Model names:** Ollama tag names (e.g., `qwen3.6:latest`, `deepseek-r1:14b`)
- **Tool calling:** Uses **ReAct** (text-based JSON extraction), not native tool_calls (Ollama doesn't support that yet)
- **Concurrency:** Ollama handles CPU/GPU scheduling; you don't need to pin devices

### Tool Calling (ReAct)

Both Optimizer and Evaluator use **ReAct** to call PubMed:

```
User: ...query the PubMed tool to find citations...
Model: I'll search for "sepsis troponin guideline"...
{"action": "tool", "tool": "search_articles", "args": {"query": "..."}}
Model: The search returned [...]. Now let me verify the PMID...
{"action": "final", "result": {...}}
```

The agentic loop parses the JSON from the model's text response. This is compatible with **any backend** (HF, vLLM, Ollama).

---

## Troubleshooting

### "Connection refused" when starting generation

**Problem:** Ollama endpoint not reachable.

**Fix:** Make sure Ollama is running in another terminal:
```bash
ollama serve
```

### "Model not found: qwen3.6:latest"

**Problem:** Qwen not downloaded or wrong name.

**Fix:**
```bash
ollama pull qwen3.6:latest
ollama list
```

### "Model not found: deepseek-r1:14b"

**Problem:** DeepSeek not downloaded.

**Fix:**
```bash
ollama pull deepseek-r1:14b
ollama list
```

### Generation is very slow

**Expected:** Ollama on MacBook (CPU or M-series GPU) will be slower than H100. Expect 1–4 min per question.

**Optimization options:**
- Enable Metal acceleration on Mac (Ollama auto-detects)
- Use smaller models (e.g., `qwen3.6:7b`, `deepseek-r1:7b` — but lower quality)
- Run concurrent questions with `generation.concurrency: 4` in the config (trades latency for throughput)

### "MEMORY ERROR" or model loading hangs

**Problem:** Not enough system RAM.

**Fix:**
- Close other apps
- Check available memory: `vm_stat` (on macOS)
- Use smaller models (7B instead of 14B/27B)

---

## Next Steps

1. ✅ **Test the connection** → run `test_ollama_connection.py`
2. ✅ **Run a smoke test** → generate 3–10 questions to validate end-to-end
3. ✅ **Full benchmark runs** → generate 500 questions per benchmark (A/B/C)
4. 🔜 **Phase 2** (next): Build the evaluation harness to score agent answers against the generated questions

---

## Config Reference

### Key Settings in `config/qgen.yaml`

| Setting | Default | Notes |
|---|---|---|
| `models.optimizer.backend` | `ollama` | Switch to `hf` or `vllm` to use other backends |
| `models.optimizer.model_id` | `qwen3.6:latest` | Ollama tag (run `ollama list` to see available) |
| `models.optimizer.endpoint` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `generation.concurrency` | `8` | Max questions in flight (tune for MacBook RAM) |
| `generation.max_iterations` | `3` | Optimizer-Evaluator refine cycles |
| `generation.max_tool_calls_per_agent` | `6` | PubMed search budget per agent call |

### To Switch Models

Edit `config/qgen.yaml` and change `model_id`:

```yaml
models:
  optimizer:
    model_id: qwen3.6:7b   # smaller, faster
    # or: deepseek-r1:7b
    # or: neural-chat:latest
```

Then run `ollama pull <name>` first, then re-run generation.

---

## Files Layout

```
Version_2/
├── test_ollama_connection.py          ← Run this first!
├── OLLAMA_SETUP.md                    ← You are here
├── Benchmark_A/Question_Generation/
│   ├── qgen/
│   │   ├── ollama_backend.py          ← NEW
│   │   ├── hf_backend.py              ← UPDATED (factory)
│   │   ├── config.py
│   │   ├── agentic_loop.py
│   │   ├── optimizer.py
│   │   ├── evaluator.py
│   │   └── orchestrator.py
│   ├── config/
│   │   ├── qgen.yaml                  ← UPDATED (ollama backend)
│   │   ├── qgen_pilot.yaml            ← UPDATED
│   │   └── qgen_smoke.yaml            ← UPDATED
│   └── outputs/
│       └── questions.jsonl            ← Generated here
├── Benchmark_B/...                    ← Same structure
└── Benchmark_C/...                    ← Same structure
```

---

**You're all set! 🚀 Start with `test_ollama_connection.py` to verify, then run a benchmark.**
