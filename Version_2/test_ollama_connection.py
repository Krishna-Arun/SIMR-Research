#!/usr/bin/env python3
"""
Test Ollama backend connection and model availability.

Run this to verify:
1. Ollama endpoint is reachable
2. Both models (Qwen 3.6 and DeepSeek-R1) are available
3. Basic chat call works for each model
"""

import sys
from pathlib import Path

# Add Benchmark A to path for imports
sys.path.insert(0, str(Path(__file__).parent / "Benchmark_A" / "Question_Generation"))

from qgen.ollama_backend import OllamaChat


def test_ollama_health():
    """Test basic endpoint connectivity."""
    print("=" * 60)
    print("Testing Ollama endpoint connectivity...")
    print("=" * 60)

    try:
        from openai import OpenAI
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=10)
        models = client.models.list()
        print(f"✓ Connected to Ollama at http://localhost:11434/v1")
        print(f"✓ Available models: {[m.id for m in models.data]}\n")
        return True
    except Exception as e:
        print(f"✗ Failed to connect to Ollama: {e}")
        print("\nMake sure Ollama is running:")
        print("  $ ollama serve")
        return False


def test_model(model_id: str, is_evaluator: bool = False):
    """Test a specific model."""
    role = "Evaluator" if is_evaluator else "Optimizer"
    print(f"Testing {role} ({model_id})...")

    try:
        cfg = {
            "model_id": model_id,
            "endpoint": "http://localhost:11434/v1",
            "temperature": 0.0 if is_evaluator else 0.2,
            "max_tokens": 512,  # Ollama may need more tokens for initial response
        }
        chat = OllamaChat(cfg)

        # Check health
        if not chat.healthy():
            print(f"  ✗ Health check failed for {model_id}")
            return False
        print(f"  ✓ Health check passed")

        # Test a simple chat call (with higher max_tokens for Ollama)
        test_msg = "Respond with any text to confirm you're working."
        result = chat.chat([{"role": "user", "content": test_msg}])

        # Accept any non-empty response as success
        if result.text and len(result.text.strip()) > 0:
            print(f"  ✓ Chat call succeeded")
            print(f"    Response: {result.text[:80]}")
            return True
        else:
            print(f"  ✗ Empty response (may need more max_tokens)")
            return False

    except Exception as e:
        print(f"  ✗ Error testing {model_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n🔧 OLLAMA CONNECTION TEST\n")

    # 1. Test endpoint
    if not test_ollama_health():
        print("\n❌ Ollama endpoint not reachable. Start Ollama first:")
        print("   $ ollama serve")
        return 1

    # 2. Test optimizer model
    print("=" * 60)
    print("Model 1: Optimizer (Qwen 3.6 27B)")
    print("=" * 60)
    qwen_ok = test_model("qwen3.6:latest", is_evaluator=False)

    # 3. Test evaluator model
    print("\n" + "=" * 60)
    print("Model 2: Evaluator (DeepSeek-R1-Distill-Qwen-14B)")
    print("=" * 60)
    deepseek_ok = test_model("deepseek-r1:14b", is_evaluator=True)

    # 4. Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if qwen_ok and deepseek_ok:
        print("✅ All tests passed! Ready to run benchmarks.")
        print("\nNext steps:")
        print("1. Start Ollama in a separate terminal:")
        print("   $ ollama serve")
        print("\n2. Run a smoke test:")
        print("   $ cd Version_2/Benchmark_A/Question_Generation")
        print("   $ python -m qgen.run_generate config/qgen_smoke.yaml --pilot")
        return 0
    else:
        print("❌ Some tests failed.")
        if not qwen_ok:
            print("\n  - Qwen 3.6 not available. Download with:")
            print("    $ ollama pull qwen3.6:latest")
        if not deepseek_ok:
            print("\n  - DeepSeek-R1 not available. Download with:")
            print("    $ ollama pull deepseek-r1:14b")
        return 1


if __name__ == "__main__":
    sys.exit(main())
