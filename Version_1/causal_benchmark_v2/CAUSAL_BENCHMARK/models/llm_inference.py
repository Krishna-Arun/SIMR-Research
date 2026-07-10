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

    # ── New two-arm format helpers ──────────────────────────────────────────
    _MARKER_PRIORITY = [
        "Troponin T", "Creatine Kinase, MB Isoenzyme", "NTproBNP",
        "Lactate Dehydrogenase (LD)", "Creatine Kinase (CK)", "Lactate", "Troponin I",
    ]

    @staticmethod
    def _numeric_series(marker_values) -> List[float]:
        """Coerce a marker's measurements to floats. Handles list[dict], list[float], or resampled dict."""
        if isinstance(marker_values, dict):
            marker_values = marker_values.get("resampled_values", [])
        out = []
        for v in marker_values:
            out.append(float(v["value"]) if isinstance(v, dict) else float(v))
        return out

    @classmethod
    def _primary_marker_name(cls, episode: Dict) -> Optional[str]:
        pm = episode.get("primary_marker")
        markers = episode.get("pre_context", {}).get("markers", {})
        if pm and pm in markers:
            return pm
        for m in cls._MARKER_PRIORITY:
            if m in markers:
                return m
        return next(iter(markers), None)

    _ARM_DESC = {
        "pci": "Percutaneous coronary intervention (PCI) — coronary revascularization via stent/angioplasty.",
        "cabg": "Coronary artery bypass grafting (CABG) — surgical revascularization.",
        "medical": "Medical management only — guideline-directed medical therapy, NO revascularization.",
        "control": "No revascularization — the patient was managed conservatively (medical management).",
        "observation": "Observation only — no procedural intervention.",
    }

    @classmethod
    def _arm_description(cls, arm: str) -> str:
        return cls._ARM_DESC.get(str(arm).lower(), f"Management approach: {arm}")

    # ── Multi-marker support ────────────────────────────────────────────────
    # Short, parser-friendly aliases for the JSON keys the model returns.
    _ALIASES = {
        "Troponin T": "troponin",
        "Creatine Kinase, MB Isoenzyme": "ck_mb",
        "Sodium": "sodium",
    }

    @classmethod
    def _alias_to_marker(cls):
        return {v: k for k, v in cls._ALIASES.items()}

    @classmethod
    def _markers_present(cls, episode: Dict) -> List[str]:
        mp = episode.get("markers_present")
        if mp:
            return list(mp)
        return list(episode.get("pre_context", {}).get("markers", {}).keys())

    @classmethod
    def _task_block(cls, episode: Dict, window_h: int) -> str:
        """Instruction asking for a per-marker JSON prediction over the post window."""
        q = int(window_h / 4)
        markers = cls._markers_present(episode)
        ids = [(cls._ALIASES.get(m, m), m) for m in markers]
        listing = "\n".join(f'  - "{a}"  ({m})' for a, m in ids)
        example = {a: {"direction": "stable", "values": [0, 0, 0, 0]} for a, _ in ids}
        return (
            f"For EACH lab below, predict its trajectory over the {window_h} hours after the index time:\n"
            f"{listing}\n\n"
            f"Return ONLY a JSON object keyed by lab id. Each entry has a direction "
            f'("rising" | "falling" | "stable") and 4 values [at {q}h, {2*q}h, {3*q}h, {window_h}h].\n'
            f"Example format:\n{json.dumps(example)}\n\n"
            f"Return ONLY the JSON, no other text."
        )

    @staticmethod
    def _values_to_trajectory(values) -> Optional[np.ndarray]:
        """Interpolate 4+ predicted values to a 96-point trajectory."""
        try:
            vals = [float(v) for v in values]
        except (ValueError, TypeError):
            return None
        if len(vals) < 2:
            return None
        return np.interp(np.linspace(0, 1, 96), np.linspace(0, 1, len(vals)), np.array(vals, float))

    @classmethod
    def _format_clinical_context_block(cls, episode: Dict) -> str:
        """Render the full safe pre-intervention chart: presentation notes, all labs, microbiology."""
        cc = episode.get("clinical_context", {})
        if not cc:
            return ""
        parts = []
        if str(cc.get("chief_complaint", "")).strip():
            parts.append(f"**Chief complaint:** {cc['chief_complaint'].strip()}")
        if str(cc.get("hpi", "")).strip():
            parts.append(f"**History of present illness:**\n{cc['hpi'].strip()}")
        if str(cc.get("physical_exam", "")).strip():
            parts.append(f"**Admission physical exam:**\n{cc['physical_exam'].strip()}")
        labs = cc.get("labs_all", {})
        if labs:
            lines = ["**All labs measured before the index (latest [range], n):**"]
            for name, s in sorted(labs.items()):
                unit = f" {s['unit']}" if s.get("unit") else ""
                lines.append(f"- {name}: {s['latest']}{unit} (range {s['min']}–{s['max']}, n={s['n']})")
            parts.append("\n".join(lines))
        micro = cc.get("microbiology", [])
        if micro:
            mlines = ["**Microbiology before the index:**"]
            for m in micro[:15]:
                org = f" → {m['organism']}" if m.get("organism") else ""
                interp = f" [{m['interpretation']}]" if m.get("interpretation") else ""
                mlines.append(f"- {m.get('specimen','')}/{m.get('test','')}{org}{interp}")
            parts.append("\n".join(mlines))
        return "\n\n".join(parts)

    # Render order priority for the full-lab block (cardiac/renal first, then the rest).
    _LAB_PRIORITY = ["Troponin T", "Creatine Kinase, MB Isoenzyme", "Creatinine", "Lactate",
                     "Urea Nitrogen", "Sodium", "Potassium", "Bicarbonate", "Anion Gap",
                     "Hemoglobin", "Hematocrit", "White Blood Cells", "Platelet Count"]

    @classmethod
    def _format_full_labs_block(cls, cc: Dict, max_chars: int = 9000) -> str:
        """Render the FULL timestamped pre-index lab series (no summary). Budget-aware:
        prioritizes cardiac/renal labs and the most-recent draws; truncates oldest first
        if over budget so the clinically-relevant recent values always survive."""
        full = cc.get("labs_full", {})
        if not full:
            return ""
        order = [l for l in cls._LAB_PRIORITY if l in full] + \
                sorted(k for k in full if k not in cls._LAB_PRIORITY)
        lines, used = [], 0
        for label in order:
            series = full[label]
            pts = [f"{p['value']:g}@{p['hours_from_index']:g}h" for p in series]
            line = f"- {label} ({len(series)}): " + ", ".join(pts)
            if used + len(line) > max_chars:
                # keep the most-recent draws that still fit
                keep = []
                for p in reversed(series):
                    cand = f"{p['value']:g}@{p['hours_from_index']:g}h"
                    if used + len(", ".join([cand] + keep)) + len(label) + 12 > max_chars:
                        break
                    keep.insert(0, cand)
                if keep:
                    lines.append(f"- {label} ({len(series)}, most recent {len(keep)}): " + ", ".join(keep))
                break
            lines.append(line); used += len(line)
        return "**All pre-index labs (value@hours-before-index):**\n" + "\n".join(lines)

    @classmethod
    def _format_chart_full(cls, episode: Dict) -> str:
        """Presentation notes + FULL timestamped labs + microbiology (pre-index only)."""
        cc = episode.get("clinical_context", {})
        if not cc:
            return ""
        parts = []
        if str(cc.get("chief_complaint", "")).strip():
            parts.append(f"**Chief complaint:** {cc['chief_complaint'].strip()}")
        if str(cc.get("hpi", "")).strip():
            parts.append(f"**History of present illness:**\n{cc['hpi'].strip()}")
        if str(cc.get("physical_exam", "")).strip():
            parts.append(f"**Admission physical exam:**\n{cc['physical_exam'].strip()}")
        full_block = cls._format_full_labs_block(cc)
        if full_block:
            parts.append(full_block)
        elif cc.get("labs_all"):                 # fallback to summary if labs_full absent
            return cls._format_clinical_context_block(episode)
        micro = cc.get("microbiology", [])
        if micro:
            mlines = ["**Microbiology before the index:**"]
            for m in micro[:15]:
                org = f" → {m['organism']}" if m.get("organism") else ""
                interp = f" [{m['interpretation']}]" if m.get("interpretation") else ""
                mlines.append(f"- {m.get('specimen','')}/{m.get('test','')}{org}{interp}")
            parts.append("\n".join(mlines))
        return "\n\n".join(parts)

    @classmethod
    def _format_marker_block(cls, pre_context: Dict) -> str:
        """Render pre-intervention markers (handles new dict / old labs-list formats)."""
        if "markers" in pre_context:
            markers = pre_context["markers"]
            if not markers:
                return "No lab data available"
            lines = ["**Cardiac Markers (pre-intervention, value @ hours-before-index):**"]
            for name, values in markers.items():
                series = cls._numeric_series(values)
                if not series:
                    continue
                # show up to the last 5 measurements with timing if available
                pts = []
                for v in values[-5:]:
                    if isinstance(v, dict):
                        pts.append(f"{float(v['value']):.3f}@{abs(v.get('hours_from_index', 0)):.0f}h")
                    else:
                        pts.append(f"{float(v):.3f}")
                lines.append(f"- {name}: {len(series)} measurements [{', '.join(pts)}], latest={series[-1]:.3f}")
            return "\n".join(lines)
        elif "labs" in pre_context:
            return LLMPredictor._format_labs_table(pre_context["labs"])
        return "No lab data available"

    def build_prompt_zero_shot(self, episode: Dict) -> str:
        """Build zero-shot prompt (no examples)."""
        # Handle both old (synthetic) and new (real) data formats
        pre_context = episode.get("pre_context", {})

        labs_table = self._format_marker_block(pre_context)
        context_block = self._format_clinical_context_block(episode)

        demographics = self._format_demographics(episode.get("demographics", {"age": "unknown", "gender": "unknown"}))
        clinical = self._format_clinical_context(episode.get("clinical_context", {"diagnoses": [], "medications": []}))

        intervention = episode["intervention"].get("type", "unknown")
        intervention_time = episode["intervention"].get(
            "date", episode["intervention"].get("datetime",
            episode["intervention"].get("index_time", "unknown")))
        window_h = episode.get("pre_context", {}).get("window_hours", 48)

        prompt = f"""You are a clinical reasoning expert. Predict how key lab values evolve following a clinical management decision.

## Patient chart up to the index time
{context_block}

## Cardiac markers to predict (pre-intervention series)
{labs_table}

## Clinical Management
{self._arm_description(intervention)}
Index time: {intervention_time}

## Task
{self._task_block(episode, window_h)}
"""
        return prompt

    def build_prompt_cot(self, episode: Dict) -> str:
        """Build chain-of-thought prompt (with reasoning steps)."""
        # Handle both old (synthetic) and new (real) data formats
        pre_context = episode.get("pre_context", {})

        labs_table = self._format_marker_block(pre_context)
        context_block = self._format_clinical_context_block(episode)

        demographics = self._format_demographics(episode.get("demographics", {"age": "unknown", "gender": "unknown"}))
        clinical = self._format_clinical_context(episode.get("clinical_context", {"diagnoses": [], "medications": []}))

        intervention = episode["intervention"].get("type", "unknown")
        intervention_time = episode["intervention"].get(
            "date", episode["intervention"].get("datetime",
            episode["intervention"].get("index_time", "unknown")))
        window_h = episode.get("pre_context", {}).get("window_hours", 48)

        prompt = f"""You are a clinical reasoning expert. Predict how key lab values evolve following a clinical management decision.

## Patient chart up to the index time
{context_block}

## Cardiac markers to predict (pre-intervention series)
{labs_table}

## Clinical Management
{self._arm_description(intervention)}
Index time: {intervention_time}

## Analysis
Think step-by-step for EACH lab:
1. Current state: what does the pre-index level and trend show?
2. Management effect: should THIS intervention move this particular lab — and which direction? (Not every lab is affected by every intervention.)
3. Timeline: how fast over {window_h} hours?

## Task
{self._task_block(episode, window_h)}
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

        # Handle both old (synthetic) and new (real) data formats
        pre_context = episode.get("pre_context", {})

        labs_table = self._format_marker_block(pre_context)
        context_block = self._format_clinical_context_block(episode)

        demographics = self._format_demographics(episode.get("demographics", {}))
        clinical = self._format_clinical_context(episode.get("clinical_context", {}))
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

Return ONLY JSON:
{{
  "troponin_direction": "rising|falling|stable",
  "estimated_values": [12h, 24h, 36h, 48h],
  "reasoning": "explanation"
}}
"""
        return prompt

    @staticmethod
    def _extract_last_json(text: str) -> Optional[Dict]:
        """Return the LAST balanced {...} object that looks like an answer.
        Robust to reasoning preambles that contain their own braces."""
        candidates = []
        for s in (i for i, c in enumerate(text) if c == "{"):
            depth = 0
            for e in range(s, len(text)):
                if text[e] == "{":
                    depth += 1
                elif text[e] == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[s:e + 1])
                        break
        answer_keys = ("estimated_values", "values", "predictions", "troponin_direction", "direction")
        for frag in reversed(candidates):
            for attempt in (frag, frag.replace("'", '"').replace("\n", " ")):
                try:
                    obj = json.loads(attempt)
                except Exception:
                    continue
                if isinstance(obj, dict) and any(k in obj for k in answer_keys):
                    return obj
        return None

    @staticmethod
    def _coerce_entry(entry):
        """From a per-marker JSON entry, return (trajectory_96, direction) or None."""
        direction = None
        values = None
        if isinstance(entry, dict):
            d = entry.get("direction", entry.get("troponin_direction"))
            direction = str(d).lower() if d is not None else None
            values = entry.get("values", entry.get("estimated_values", entry.get("predictions")))
        elif isinstance(entry, list):
            values = entry
        if not values:
            return None
        traj = LLMPredictor._values_to_trajectory(values)
        if traj is None:
            return None
        # Derive direction from the trajectory when not explicitly (and validly) provided.
        if direction not in ("rising", "falling", "stable"):
            rel = (traj[-1] - traj[0]) / (abs(traj[0]) + 1e-6)
            direction = "stable" if abs(rel) < 0.10 else ("rising" if rel > 0 else "falling")
        return traj, direction

    @staticmethod
    def _top_level_json_objects(text: str) -> List[str]:
        """All TOP-LEVEL balanced {...} substrings (skips nested objects)."""
        objs, i, n = [], 0, len(text)
        while i < n:
            if text[i] == "{":
                depth, found = 0, False
                for e in range(i, n):
                    if text[e] == "{":
                        depth += 1
                    elif text[e] == "}":
                        depth -= 1
                        if depth == 0:
                            objs.append(text[i:e + 1]); i = e + 1; found = True; break
                if not found:
                    break
            else:
                i += 1
        return objs

    def parse_response(self, response_text: str, episode: Dict) -> Dict[str, Dict]:
        """
        Parse a per-marker LLM response into {marker: {"trajectory": ndarray, "direction": str}}.
        Picks the TOP-LEVEL container whose keys are marker ids (multi-marker schema),
        falling back to the legacy single-marker schema and then a numeric fallback.
        Robust to reasoning preambles. Returns {} if nothing parseable.
        """
        import re
        out: Dict[str, Dict] = {}
        try:
            clean = re.sub(r"<think>.*?</think>", " ", response_text, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"</?think>", " ", clean, flags=re.IGNORECASE)
            markers = self._markers_present(episode)
            alias_to_marker = self._alias_to_marker()
            valid_keys = set(alias_to_marker) | set(markers)
            single_keys = ("estimated_values", "values", "predictions", "troponin_direction", "direction")

            container, single = None, None
            for frag in reversed(self._top_level_json_objects(clean)):
                obj = None
                for attempt in (frag, frag.replace("'", '"').replace("\n", " ")):
                    try:
                        obj = json.loads(attempt); break
                    except Exception:
                        continue
                if not isinstance(obj, dict):
                    continue
                if container is None and (set(obj.keys()) & valid_keys):
                    container = obj
                if single is None and any(k in obj for k in single_keys):
                    single = obj

            pm = episode.get("primary_marker") or (markers[0] if markers else "Troponin T")
            if container:  # (a) multi-marker
                for key, entry in container.items():
                    marker = alias_to_marker.get(key) or (key if key in markers else None)
                    if marker is None:
                        continue
                    c = self._coerce_entry(entry)
                    if c:
                        out[marker] = {"trajectory": c[0], "direction": c[1]}
            if not out and single is not None:  # (b) legacy single-marker -> primary
                c = self._coerce_entry(single)
                if c:
                    out[pm] = {"trajectory": c[0], "direction": c[1]}
            if not out:  # (c) numeric fallback -> primary
                numbers = re.findall(r'-?\d+\.?\d+', clean)
                if len(numbers) >= 4:
                    c = self._coerce_entry([float(n) for n in numbers[-4:]])
                    if c:
                        out[pm] = {"trajectory": c[0], "direction": c[1]}
        except Exception as e:
            logger.debug(f"Error parsing response: {str(e)[:120]}")
        return out

    # ── Task C: counterfactual SCALAR outcome prediction ─────────────────────
    # `outcomes` is a list of descriptors from run_taskC.py, each:
    #   {"id": "troponin", "key": "peak_troponin_72h",
    #    "display": "peak troponin T", "unit": "ng/mL", "kind": "level"|"delta",
    #    "desc": "the peak troponin T over the 72h after the index time"}
    _CF_DIR_HELP = ('"direction" is "rising" | "falling" | "stable" describing the marker '
                    "versus its pre-index baseline.")

    def build_prompt_counterfactual(self, episode: Dict, treatment: str,
                                    outcomes: List[Dict]) -> str:
        """Prompt the model to predict scalar outcomes UNDER A SPECIFIED management
        (factual or counterfactual). The observed post-index outcome is withheld.
        Uses the FULL timestamped pre-index chart (no summary) when available."""
        ctx = self._format_chart_full(episode)
        pre = self._format_marker_block(episode.get("pre_context", {}))
        arm = self._arm_description(treatment)
        idx_t = episode["intervention"].get("index_time", "the index time")
        listing = "\n".join(
            f'  - "{o["id"]}": predict {o["desc"]} (in {o["unit"]}).' for o in outcomes)
        example = {o["id"]: {"value": 0.0, "direction": "stable",
                             "justification": "1-2 sentences citing THIS patient's specific "
                             "findings and the causal reason this management changes the outcome"}
                   for o in outcomes}
        reason = ""
        if self.prompt_style == "cot":
            reason = ("\n## Reasoning\nThink step by step: (1) baseline level/trend, "
                      "(2) how THIS management causally affects each marker over 72h "
                      "and in which direction, (3) the most likely numeric value.\n")
        return f"""You are a clinical reasoning expert estimating outcomes of a management decision.

## Patient chart up to the index time (pre-treatment only)
{ctx}

## Pre-intervention cardiac markers
{pre}

## Management actually assigned for this prediction
{arm}
Index time: {idx_t}
{reason}
## Task
Assuming the management above, predict each outcome over the 72 hours AFTER the index time:
{listing}
{self._CF_DIR_HELP}

Return ONLY a JSON object keyed by id, each with a numeric "value", a "direction", and a
"justification" (1-2 sentences that reference THIS patient's specific findings and the causal
mechanism by which the management changes the outcome — not a generic statement).
Example format:
{json.dumps(example)}

Return ONLY the JSON, no other text."""

    @staticmethod
    def _to_float(v) -> Optional[float]:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            import re
            m = re.search(r"-?\d+\.?\d*", v.replace(",", ""))
            if m:
                try:
                    return float(m.group())
                except ValueError:
                    return None
        return None

    @staticmethod
    def _norm_dir(d) -> Optional[str]:
        if d is None:
            return None
        d = str(d).lower()
        for k in ("rising", "falling", "stable"):
            if k in d:
                return k
        if d in ("up", "increase", "increasing", "higher"):
            return "rising"
        if d in ("down", "decrease", "decreasing", "lower"):
            return "falling"
        return None

    def parse_scalar(self, response_text: str, outcomes: List[Dict]) -> Dict[str, Dict]:
        """Parse {id: {"value": float, "direction": str}} from the model response.
        Robust to <think> preambles and quote/format noise."""
        import re
        out: Dict[str, Dict] = {}
        ids = {o["id"] for o in outcomes}
        try:
            clean = re.sub(r"<think>.*?</think>", " ", response_text, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"</?think>", " ", clean, flags=re.IGNORECASE)
            for frag in reversed(self._top_level_json_objects(clean)):
                obj = None
                for attempt in (frag, frag.replace("'", '"').replace("\n", " ")):
                    try:
                        obj = json.loads(attempt); break
                    except Exception:
                        continue
                if not isinstance(obj, dict) or not (set(obj.keys()) & ids):
                    continue
                for mid in ids:
                    entry = obj.get(mid)
                    if isinstance(entry, dict):
                        j = entry.get("justification", entry.get("rationale", ""))
                        out[mid] = {"value": self._to_float(entry.get("value")),
                                    "direction": self._norm_dir(entry.get("direction")),
                                    "justification": str(j).strip() if j else ""}
                    elif entry is not None:
                        out[mid] = {"value": self._to_float(entry), "direction": None,
                                    "justification": ""}
                if out:
                    break
        except Exception as e:
            logger.debug(f"Error parsing scalar response: {str(e)[:120]}")
        return out

    def predict_scalar(self, episode: Dict, treatment: str, outcomes: List[Dict],
                       with_confidence: bool = True) -> Dict[str, Dict]:
        """Predict scalar outcomes (value + direction + activation confidence) under
        `treatment`. Subclasses implement generation; this base raises."""
        raise NotImplementedError

    def predict_multiarm(self, episode: Dict, arms: List[str], outcomes: List[Dict],
                         with_confidence: bool = True) -> Dict[str, Dict[str, Dict]]:
        """Predict every outcome under EACH treatment arm → {arm: {outcome_id: {...}}}.
        The model's estimated pairwise effect for arms (a,b) is then prediction[a] − prediction[b],
        and its best-arm recommendation is the arm optimizing the (lower-is-better) outcome.
        Generic: loops predict_scalar per arm, so it works for HF / Mock / Ollama predictors."""
        return {arm: self.predict_scalar(episode, arm, outcomes, with_confidence=with_confidence)
                for arm in arms}


class HuggingFaceLLMPredictor(LLMPredictor):
    """Predict using Hugging Face Transformers."""

    def __init__(self, model_name: str, prompt_style: str = "cot",
                 load_in_4bit: Optional[bool] = None):
        super().__init__(model_name, prompt_style)
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            self.device = "cuda" if torch.cuda.is_available() else "cpu"

            # Auto-enable 4-bit quantization for large models on GPU unless overridden.
            # Env override: CAUSAL_LOAD_4BIT=1/0
            import os
            if load_in_4bit is None:
                env = os.environ.get("CAUSAL_LOAD_4BIT")
                if env is not None:
                    load_in_4bit = env == "1"
                else:
                    # Only the very largest models need 4-bit (and thus accelerate/device_map).
                    # 7B/14B/32B all fit a single 80GB H100 in fp16 with a plain .to(cuda).
                    big = any(s in model_name.lower() for s in ["70b", "72b", "65b", "mixtral"])
                    load_in_4bit = big and self.device == "cuda"

            logger.info(f"Loading {model_name} (device={self.device}, 4bit={load_in_4bit})...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            kwargs = {"trust_remote_code": True}
            if load_in_4bit and self.device == "cuda":
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )
                kwargs["device_map"] = "auto"
                self.model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
            elif self.device == "cuda":
                # Single-GPU fp16 load WITHOUT device_map (avoids the accelerate dependency,
                # which is currently broken in the py314 module stack on this cluster).
                kwargs["dtype"] = torch.float16
                self.model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs).to("cuda")
            else:
                kwargs["torch_dtype"] = torch.float32
                self.model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs).to(self.device)

            self.model.eval()
            logger.info(f"Loaded {model_name} on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load {model_name}: {e}")
            raise

    def _render_chat(self, prompt: str) -> str:
        if getattr(self.tokenizer, "chat_template", None):
            msgs = [{"role": "user", "content": prompt}]
            try:
                # Qwen3 supports a thinking toggle; disable it so the model emits the
                # JSON answer directly (keeps the run tractable). Harmless for other templates.
                return self.tokenizer.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            except TypeError:
                return self.tokenizer.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=True)
        return prompt

    def _direction_confidence(self, episode: Dict) -> Optional[Dict]:
        """TRUE logit-based confidence: P(rising/falling/stable) for the primary marker,
        from the model's own output distribution (constrained continuation scoring)."""
        import torch
        import torch.nn.functional as F
        pm = episode.get("primary_marker", "Troponin T")
        window_h = episode.get("pre_context", {}).get("window_hours", 96)
        pre = self._format_marker_block(episode.get("pre_context", {}))
        arm = self._arm_description(episode["intervention"]["type"])
        base = (f"{pre}\n\n## Clinical Management\n{arm}\n\n"
                f"Over the {window_h} hours after the index time, the {pm} level will most likely be")
        base = self._render_chat(base)
        options = {"rising": " rising", "falling": " falling", "stable": " stable"}
        dev = "cuda" if self.device == "cuda" else "cpu"
        base_ids = self.tokenizer(base, return_tensors="pt").input_ids
        nb = base_ids.shape[1]
        logps = {}
        for k, opt in options.items():
            full = self.tokenizer(base + opt, return_tensors="pt").input_ids
            with torch.no_grad():
                logits = self.model(full.to(dev)).logits[0]
            lp = 0.0
            for pos in range(nb, full.shape[1]):
                tok = full[0, pos]
                lp += float(F.log_softmax(logits[pos - 1], dim=-1)[tok])
            logps[k] = lp
        mx = max(logps.values())
        exps = {k: float(np.exp(v - mx)) for k, v in logps.items()}
        Z = sum(exps.values()) or 1.0
        probs = {k: exps[k] / Z for k in exps}
        direction = max(probs, key=probs.get)
        return {"marker": pm, "probs": probs, "direction": direction, "p": probs[direction]}

    def _score_continuations(self, base: str, options: Dict[str, str]) -> Dict:
        """Constrained-continuation scoring: P(option) from the model's own activations
        (the same logit-based technique as _direction_confidence, factored for reuse)."""
        import torch
        import torch.nn.functional as F
        base = self._render_chat(base)
        dev = "cuda" if self.device == "cuda" else "cpu"
        nb = self.tokenizer(base, return_tensors="pt").input_ids.shape[1]
        logps = {}
        for k, opt in options.items():
            full = self.tokenizer(base + opt, return_tensors="pt").input_ids
            with torch.no_grad():
                logits = self.model(full.to(dev)).logits[0]
            lp = 0.0
            for pos in range(nb, full.shape[1]):
                lp += float(F.log_softmax(logits[pos - 1], dim=-1)[full[0, pos]])
            logps[k] = lp
        mx = max(logps.values())
        exps = {k: float(np.exp(v - mx)) for k, v in logps.items()}
        Z = sum(exps.values()) or 1.0
        probs = {k: exps[k] / Z for k in exps}
        d = max(probs, key=probs.get)
        return {"probs": probs, "direction": d, "p": probs[d]}

    def _direction_confidence_cf(self, episode: Dict, treatment: str, disp: str) -> Optional[Dict]:
        """Activation-derived confidence over rising/falling/stable for one marker under a
        specified (counterfactual or factual) treatment."""
        pre = self._format_marker_block(episode.get("pre_context", {}))
        arm = self._arm_description(treatment)
        base = (f"{pre}\n\n## Management\n{arm}\n\n"
                f"Under this management, over the 72 hours after the index time the patient's "
                f"{disp} will most likely")
        out = self._score_continuations(base, {"rising": " rise", "falling": " fall",
                                               "stable": " stay stable"})
        out["marker"] = disp
        return out

    def predict_scalar(self, episode: Dict, treatment: str, outcomes: List[Dict],
                       with_confidence: bool = True) -> Dict[str, Dict]:
        import torch, os
        result = {o["id"]: {"value": None, "direction": None, "confidence": None, "justification": ""} for o in outcomes}
        try:
            prompt = self.build_prompt_counterfactual(episode, treatment, outcomes)
            text = self._render_chat(prompt)
            inputs = {k: v.to("cuda" if self.device == "cuda" else "cpu")
                      for k, v in self.tokenizer(text, return_tensors="pt").items()}
            prompt_len = inputs["input_ids"].shape[1]
            max_new = int(os.environ.get("CAUSAL_MAX_NEW_TOKENS_SCALAR", "512"))
            with torch.no_grad():
                outputs = self.model.generate(**inputs, max_new_tokens=max_new, do_sample=False,
                                              pad_token_id=self.tokenizer.pad_token_id)
            response = self.tokenizer.decode(outputs[0][prompt_len:], skip_special_tokens=True)
            parsed = self.parse_scalar(response, outcomes)
            for o in outcomes:
                mid = o["id"]
                p = parsed.get(mid, {})
                conf = None
                if with_confidence:
                    try:
                        conf = self._direction_confidence_cf(episode, treatment, o["display"])
                    except Exception as e:
                        logger.debug(f"cf-confidence failed: {e}")
                result[mid] = {"value": p.get("value"), "direction": p.get("direction"),
                               "confidence": conf, "justification": p.get("justification", "")}
        except Exception as e:
            logger.error(f"predict_scalar error: {e}")
        return result

    def predict(self, episode: Dict, with_confidence: bool = True) -> Optional[Dict]:
        """Generate per-marker predictions (greedy) + logit-based direction confidence.
        Returns {"trajectories": {m: ndarray}, "directions": {m: str}, "confidence": {...}}.
        with_confidence=False skips the logit-confidence pass (used for the cheap flip run)."""
        try:
            import torch, os
            if self.prompt_style == "zero_shot":
                prompt = self.build_prompt_zero_shot(episode)
            elif self.prompt_style == "cot":
                prompt = self.build_prompt_cot(episode)
            else:
                prompt = self.build_prompt_few_shot(episode)

            max_new = int(os.environ.get("CAUSAL_MAX_NEW_TOKENS", "1024"))
            text = self._render_chat(prompt)
            inputs = self.tokenizer(text, return_tensors="pt")
            inputs = {k: v.to("cuda" if self.device == "cuda" else "cpu") for k, v in inputs.items()}
            prompt_len = inputs["input_ids"].shape[1]

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs, max_new_tokens=max_new, do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id)

            response = self.tokenizer.decode(outputs[0][prompt_len:], skip_special_tokens=True)
            parsed = self.parse_response(response, episode)
            if not parsed:
                logger.debug(f"Unparseable response for {episode.get('episode_id')}: {response[:120]}")
                return None

            trajectories = {m: parsed[m]["trajectory"] for m in parsed}
            directions = {m: parsed[m]["direction"] for m in parsed}
            confidence = None
            if with_confidence:
                try:
                    confidence = self._direction_confidence(episode)
                except Exception as e:
                    logger.debug(f"confidence calc failed: {e}")
            return {"trajectories": trajectories, "directions": directions, "confidence": confidence}

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

    def predict(self, episode: Dict, with_confidence: bool = True) -> Optional[Dict]:
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
            parsed = self.parse_response(response_text, episode)
            if parsed:
                return {
                    "trajectories": {m: parsed[m]["trajectory"] for m in parsed},
                    "directions": {m: parsed[m]["direction"] for m in parsed},
                    "confidence": None,   # API/Ollama: no logit access
                }

        except Exception as e:
            logger.error(f"Error with Ollama: {e}")

        return None

    def predict_scalar(self, episode: Dict, treatment: str, outcomes: List[Dict],
                       with_confidence: bool = True) -> Dict[str, Dict]:
        """Ollama scalar prediction (no logit access -> confidence=None)."""
        result = {o["id"]: {"value": None, "direction": None, "confidence": None, "justification": ""} for o in outcomes}
        try:
            prompt = self.build_prompt_counterfactual(episode, treatment, outcomes)
            r = self.requests.post(f"{self.base_url}/api/generate",
                                   json={"model": self.model_name, "prompt": prompt,
                                         "stream": False, "temperature": 0.0}, timeout=120)
            if r.status_code != 200:
                return result
            parsed = self.parse_scalar(r.json().get("response", ""), outcomes)
            for o in outcomes:
                p = parsed.get(o["id"], {})
                result[o["id"]] = {"value": p.get("value"), "direction": p.get("direction"),
                                   "confidence": None, "justification": p.get("justification", "")}
        except Exception as e:
            logger.error(f"Ollama predict_scalar error: {e}")
        return result


class MockLLMPredictor(LLMPredictor):
    """Mock predictor for testing: intervention-aware per-marker synthetic predictions.

    Encodes a *correct* clinical prior so the pipeline (and the negative-control /
    calibration logic) can be validated without a GPU:
      - PCI raises injury markers (troponin, CK-MB) then they fall
      - PCI does NOT move the negative control (sodium) -> 'stable'
    """

    _POSITIVE = {"Troponin T", "Creatine Kinase, MB Isoenzyme"}

    def predict(self, episode: Dict, with_confidence: bool = True) -> Dict:
        pre = episode.get("pre_context", {}).get("markers", {})
        markers = self._markers_present(episode)
        is_pci = "pci" in episode["intervention"]["type"].lower() or "cabg" in episode["intervention"]["type"].lower()

        trajectories, directions = {}, {}
        for m in markers:
            series = self._numeric_series(pre.get(m, []))
            base = series[-1] if series else (0.05 if "Tropon" in m else 100.0)
            if m in self._POSITIVE and is_pci:
                pts = [base, base * 1.3, base * 1.5, base * 1.2, base * 0.95, base * 0.85, base * 0.8, base * 0.78]
                directions[m] = "rising"
            elif m in self._POSITIVE:
                pts = list(np.linspace(base, base * 0.85, 8)); directions[m] = "falling"
            else:
                # negative control (sodium): no intervention effect
                pts = [base] * 8; directions[m] = "stable"
            trajectories[m] = np.interp(np.linspace(0, 1, 96), np.linspace(0, 1, len(pts)), np.array(pts, float))

        # synthetic but plausible logit-style confidence on the primary marker
        pm = episode.get("primary_marker", "Troponin T")
        d = directions.get(pm, "stable")
        p = 0.8 if (pm in self._POSITIVE and is_pci) else 0.55
        probs = {"rising": 0.1, "falling": 0.1, "stable": 0.1}
        probs[d] = p
        s = sum(probs.values()); probs = {k: v / s for k, v in probs.items()}
        confidence = {"marker": pm, "probs": probs, "direction": d, "p": probs[d]}

        return {"trajectories": trajectories, "directions": directions, "confidence": confidence}

    def predict_scalar(self, episode: Dict, treatment: str, outcomes: List[Dict],
                       with_confidence: bool = True) -> Dict[str, Dict]:
        """Mock scalar prediction encoding a correct clinical prior, for GPU-free pipeline tests:
        PCI raises injury markers (troponin/CK-MB) and creatinine (contrast nephropathy);
        conservative management lets injury markers fall; lactate ~ unchanged."""
        is_pci = "pci" in treatment.lower() or "cabg" in treatment.lower()
        result = {}
        for o in outcomes:
            base = o.get("baseline")
            base = float(base) if base is not None else (0.05 if "trop" in o["id"] else 1.0)
            injury = bool(o.get("positive"))
            renal = "creatin" in o["id"].lower()
            if o["kind"] == "delta":            # creatinine Δ
                value = 0.3 if (is_pci and renal) else (0.0)
                direction = "rising" if value > 0.05 else "stable"
            elif injury:                        # troponin / CK-MB level
                value = base * (1.6 if is_pci else 0.85)
                direction = "rising" if is_pci else "falling"
            else:                               # lactate or other level
                value = base
                direction = "stable"
            probs = {"rising": 0.15, "falling": 0.15, "stable": 0.15}
            probs[direction] = 0.7
            s = sum(probs.values()); probs = {k: v / s for k, v in probs.items()}
            # templated, patient-specific justification (cites a real chart number) for testing the rubric
            bs = episode.get("baseline_summary", {}).get("Troponin T", {})
            cr = episode.get("clinical_context", {}).get("labs_all", {}).get("Creatinine", {})
            cite = f"creatinine {cr.get('latest')}" if cr else (f"troponin {bs.get('last_pre_value')}" if bs else "the presentation")
            verb = "raises" if direction in ("rising",) else ("lowers" if direction == "falling" else "does not change")
            just = f"Given this patient's {cite}, {treatment} {verb} {o['display']} via the expected mechanism."
            result[o["id"]] = {"value": round(float(value), 4), "direction": direction,
                               "justification": just,
                               "confidence": {"marker": o["display"], "probs": probs,
                                              "direction": direction, "p": probs[direction]}}
        return result


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
