"""
llm_inference.py

Unified inference interface for open-source LLMs.

Supports:
- Qwen (via Hugging Face or local)
- DeepSeek (via Hugging Face or local)
- Llama 2/3 (via Hugging Face or local)
- Mistral (via Hugging Face or local)
- Phi-3, others

Provides:
- Standardized prompt templates
- Few-shot learning support
- Chain-of-thought prompting
- Structured output parsing
"""

import json
import numpy as np
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMPredictor(ABC):
    """Base class for LLM-based trajectory prediction."""

    def __init__(self, model_name: str, prompt_style: str = "cot"):
        """
        Args:
            model_name: Model identifier
            prompt_style: "zero_shot", "few_shot", "cot" (chain-of-thought)
        """
        self.model_name = model_name
        self.prompt_style = prompt_style

    @abstractmethod
    def predict(self, episode: Dict) -> np.ndarray:
        """
        Predict trajectory for an episode.

        Args:
            episode: Episode dict with pre_context, intervention, post_trajectory keys

        Returns:
            np.ndarray of predicted values (resampled to 96 timepoints)
        """
        pass

    @staticmethod
    def _format_labs_table(labs: List[Dict]) -> str:
        """Format lab measurements as a readable table."""
        lines = []
        lines.append("| DateTime | Lab Name | Value | Unit | Flag |")
        lines.append("|----------|----------|-------|------|------|")

        for lab in labs[-20:]:  # Last 20 measurements
            dt = lab["datetime"][:16]
            name = lab["label"][:15]
            val = f"{lab['value']:.2f}"
            unit = lab["unit"][:8]
            flag = lab.get("flag", "")
            lines.append(f"| {dt} | {name} | {val} | {unit} | {flag} |")

        return "\n".join(lines)

    @staticmethod
    def _format_demographics(demographics: Dict) -> str:
        """Format demographics as text."""
        return (
            f"Age: {demographics['age']} years, "
            f"Gender: {demographics['gender']}"
        )

    @staticmethod
    def _format_clinical_context(context: Dict) -> str:
        """Format diagnoses and medications."""
        diag_str = "; ".join(context.get("diagnoses", [])[:5]) or "Not recorded"
        med_str = ", ".join(context.get("medications", [])[:5]) or "Not recorded"
        return f"Diagnoses: {diag_str}\nMedications: {med_str}"

    def build_prompt_zero_shot(self, episode: Dict) -> str:
        """Build zero-shot prompt (no examples)."""
        labs_table = self._format_labs_table(episode["pre_context"]["labs"])
        demographics = self._format_demographics(episode["demographics"])
        clinical = self._format_clinical_context(episode["clinical_context"])

        intervention = episode["intervention"]["type"]
        intervention_time = episode["intervention"]["datetime"]

        prompt = f"""You are a clinical reasoning expert. Your task is to predict the trajectory of key lab values following a medical intervention.

## Patient Context
{demographics}

## Clinical Context
{clinical}

## Lab Measurements (last 48 hours before intervention)
{labs_table}

## Intervention
Type: {intervention}
Time: {intervention_time}

## Task
Based on the patient's lab history and the intervention applied, predict what will happen to the key lab values over the next 48 hours.

For Troponin I specifically:
- Will it rise, fall, or stay stable?
- By how much?
- In what timeframe?

Please provide:
1. Expected direction (rising, falling, stable)
2. Estimated values at 12h, 24h, 36h, 48h post-intervention
3. Reasoning based on the intervention type and patient status

Return your answer as a JSON object with:
{{
  "prediction_summary": "brief summary",
  "troponin_direction": "rising|falling|stable",
  "estimated_values": [12h_value, 24h_value, 36h_value, 48h_value],
  "reasoning": "explanation"
}}
"""
        return prompt

    def build_prompt_cot(self, episode: Dict) -> str:
        """Build chain-of-thought prompt (with reasoning steps)."""
        labs_table = self._format_labs_table(episode["pre_context"]["labs"])
        demographics = self._format_demographics(episode["demographics"])
        clinical = self._format_clinical_context(episode["clinical_context"])

        intervention = episode["intervention"]["type"]
        intervention_time = episode["intervention"]["datetime"]

        prompt = f"""You are a clinical reasoning expert. Your task is to predict the trajectory of key lab values following a medical intervention.

## Patient Context
{demographics}

## Clinical Context
{clinical}

## Lab Measurements (last 48 hours before intervention)
{labs_table}

## Intervention
Type: {intervention}
Time: {intervention_time}

## Analysis Instructions
Think step-by-step about:
1. Current patient status: What do the lab values tell you about the patient's current state?
2. Intervention effect: How should this {intervention} affect the relevant lab values?
3. Expected timeline: What is the typical response timeline for this intervention?
4. Complicating factors: Are there any comorbidities or other factors that might change the expected response?

## Task
Based on your step-by-step analysis, predict the trajectory of Troponin I over the next 48 hours.

Provide your answer as JSON:
{{
  "step1_current_status": "assessment of current patient state",
  "step2_intervention_effect": "expected physiological effect",
  "step3_timeline": "expected response timeline",
  "step4_complications": "any factors that might alter response",
  "troponin_direction": "rising|falling|stable",
  "estimated_values": [value_12h, value_24h, value_36h, value_48h],
  "confidence": 0.0-1.0,
  "reasoning": "final explanation"
}}
"""
        return prompt

    def build_prompt_few_shot(self, episode: Dict, few_shot_examples: List[Dict] = None) -> str:
        """Build few-shot prompt (with examples)."""
        # Start with examples
        examples_text = ""
        if few_shot_examples:
            for i, ex in enumerate(few_shot_examples[:2]):  # Use 2 examples
                examples_text += f"\n### Example {i+1}\n"
                ex_labs = self._format_labs_table(ex.get("pre_context", {}).get("labs", []))
                examples_text += f"Lab data:\n{ex_labs}\n"
                examples_text += f"Outcome: {json.dumps(ex.get('ground_truth', {}), indent=2)}\n"

        labs_table = self._format_labs_table(episode["pre_context"]["labs"])
        demographics = self._format_demographics(episode["demographics"])
        clinical = self._format_clinical_context(episode["clinical_context"])
        intervention = episode["intervention"]["type"]

        prompt = f"""You are a clinical expert at predicting lab trajectories after medical interventions.

## Previous Examples
{examples_text}

## New Patient
{demographics}

{clinical}

## Lab Data
{labs_table}

## Intervention: {intervention}

Predict the next 48 hours of Troponin I trajectory.

{{
  "troponin_direction": "rising|falling|stable",
  "estimated_values": [12h, 24h, 36h, 48h],
  "reasoning": "explanation"
}}
"""
        return prompt

    def parse_response(self, response_text: str) -> Optional[Dict]:
        """
        Parse LLM response to extract predictions.

        Returns:
            Dict with keys: direction, values, confidence
        """
        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)

                # Extract trajectory values
                values = data.get("estimated_values", [])
                if not values:
                    # Try alternative keys
                    values = data.get("values", data.get("predictions", []))

                # Pad or truncate to 96 timepoints
                if len(values) < 4:
                    logger.warning(f"Got {len(values)} predicted values, expected 4+")
                    return None

                # Interpolate to 96 timepoints
                trajectory = np.interp(
                    np.linspace(0, 3, 96),  # 4 time points (12h, 24h, 36h, 48h)
                    np.linspace(0, 3, len(values)),
                    np.array(values, dtype=float)
                )

                return {
                    "trajectory": trajectory,
                    "direction": data.get("troponin_direction", "stable"),
                    "confidence": data.get("confidence", 0.5),
                    "raw_response": data,
                }

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from response: {response_text[:200]}")

        return None


class HuggingFaceLLMPredictor(LLMPredictor):
    """Predict using Hugging Face Transformers."""

    def __init__(self, model_name: str, prompt_style: str = "cot"):
        super().__init__(model_name, prompt_style)
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            logger.info(f"Loading {model_name} from Hugging Face...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_8bit=True,
            )
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loaded {model_name} on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load {model_name}: {e}")
            raise

    def predict(self, episode: Dict) -> Optional[np.ndarray]:
        """Generate prediction using HuggingFace model."""
        try:
            # Build prompt
            if self.prompt_style == "zero_shot":
                prompt = self.build_prompt_zero_shot(episode)
            elif self.prompt_style == "cot":
                prompt = self.build_prompt_cot(episode)
            else:
                prompt = self.build_prompt_few_shot(episode)

            # Tokenize
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

            # Generate (with reasonable max length)
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=500,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
            )

            # Decode
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

            # Parse response
            parsed = self.parse_response(response)
            if parsed:
                return parsed["trajectory"]

        except Exception as e:
            logger.error(f"Error generating prediction: {e}")

        return None


class OllamaLLMPredictor(LLMPredictor):
    """Predict using Ollama (local inference)."""

    def __init__(self, model_name: str, prompt_style: str = "cot", base_url: str = "http://localhost:11434"):
        super().__init__(model_name, prompt_style)
        self.base_url = base_url
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("requests library required for Ollama")

    def predict(self, episode: Dict) -> Optional[np.ndarray]:
        """Generate prediction using Ollama local model."""
        try:
            # Build prompt
            if self.prompt_style == "zero_shot":
                prompt = self.build_prompt_zero_shot(episode)
            elif self.prompt_style == "cot":
                prompt = self.build_prompt_cot(episode)
            else:
                prompt = self.build_prompt_few_shot(episode)

            # Call Ollama
            response = self.requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=120,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return None

            response_text = response.json().get("response", "")

            # Parse response
            parsed = self.parse_response(response_text)
            if parsed:
                return parsed["trajectory"]

        except Exception as e:
            logger.error(f"Error with Ollama: {e}")

        return None


class MockLLMPredictor(LLMPredictor):
    """Mock predictor for testing (returns synthetic predictions)."""

    def predict(self, episode: Dict) -> np.ndarray:
        """Return a simple synthetic trajectory."""
        # Extract baseline from pre-context
        latest_trops = [
            lab["value"] for lab in episode["pre_context"]["labs"]
            if lab["label"] == "Troponin I"
        ]

        baseline = latest_trops[-1] if latest_trops else 0.05

        # Synthetic trajectory based on intervention
        intervention = episode["intervention"]["type"]
        if "pci" in intervention.lower() or "cabg" in intervention.lower():
            # Troponin expected to rise then fall for cardiac intervention
            trajectory = np.array([
                baseline,
                baseline * 1.2,
                baseline * 1.4,
                baseline * 1.2,
                baseline * 0.9,
                baseline * 0.8,
                baseline * 0.75,
                baseline * 0.7,
            ] + [baseline * 0.7] * 88)
        elif "antibiotic" in intervention.lower():
            # Slow response for antibiotics
            trajectory = np.linspace(baseline, baseline * 0.8, 96)
        else:
            # Default: slight decline
            trajectory = np.linspace(baseline, baseline * 0.85, 96)

        return trajectory


def create_predictor(model_name: str,
                    prompt_style: str = "cot",
                    backend: str = "auto") -> LLMPredictor:
    """
    Factory function to create appropriate predictor.

    Args:
        model_name: Model identifier (e.g., "Qwen/Qwen2-7B", "ollama/qwen")
        prompt_style: "zero_shot", "few_shot", or "cot"
        backend: "huggingface", "ollama", "mock", or "auto"

    Returns:
        LLMPredictor instance
    """
    if backend == "mock":
        return MockLLMPredictor(model_name, prompt_style)

    if backend == "ollama" or model_name.startswith("ollama/"):
        model_name_clean = model_name.replace("ollama/", "")
        return OllamaLLMPredictor(model_name_clean, prompt_style)

    if backend == "huggingface" or backend == "auto":
        return HuggingFaceLLMPredictor(model_name, prompt_style)

    raise ValueError(f"Unknown backend: {backend}")
