import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import SCHEMA_PATH
from .gemini_runner import run_structured_prompt


KEYWORDS = {
    "escalation": [
        "strike",
        "missile",
        "attack",
        "retaliation",
        "mobilization",
        "air defense",
        "ballistic",
    ],
    "deescalation": [
        "ceasefire",
        "talks",
        "negotiation",
        "mediated",
        "truce",
        "de-escalation",
    ],
    "succession": [
        "leadership",
        "succession",
        "interim government",
        "transition council",
        "power vacuum",
        "elite split",
    ],
    "humanitarian": [
        "displaced",
        "casualties",
        "civilian",
        "hospital",
        "shortage",
        "refugee",
    ],
}

ACTORS = [
    "Iran",
    "IRGC",
    "Supreme Leader",
    "President",
    "Israel",
    "United States",
    "Russia",
    "China",
    "Hezbollah",
    "Gulf states",
    "opposition",
]


def summarize_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    actor_counter = Counter()
    keyword_counter = Counter()
    source_counter = Counter()
    evidence = []

    for item in items:
        source_counter[item["source"]] += 1
        text = " ".join(
            filter(
                None,
                [
                    item.get("title", ""),
                    item.get("content_text", ""),
                ],
            )
        )
        text_lower = text.lower()
        for actor in ACTORS:
            pattern = re.escape(actor.lower())
            hits = len(re.findall(pattern, text_lower))
            if hits:
                actor_counter[actor] += hits
        for bucket, words in KEYWORDS.items():
            keyword_counter[bucket] += sum(text_lower.count(word) for word in words)
        evidence.append(
            {
                "source": item["source"],
                "title": item.get("title", ""),
                "published_at": item.get("published_at"),
                "url": item.get("url"),
                "snippet": text[:500],
            }
        )

    escalation = keyword_counter["escalation"]
    deescalation = keyword_counter["deescalation"]
    raw_score = escalation - deescalation
    tension_index = round(50 + 10 * math.tanh(raw_score / 10.0) * 5, 1)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "item_count": len(items),
        "source_mix": dict(source_counter),
        "top_actors": actor_counter.most_common(12),
        "keyword_counts": dict(keyword_counter),
        "tension_index": max(0.0, min(100.0, tension_index)),
        "evidence": evidence[:20],
    }


def build_prompt(summary: Dict[str, Any], language: str = "zh") -> str:
    schema = Path(SCHEMA_PATH).read_text(encoding="utf-8")
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    natural_language_rule = (
        "Use Simplified Chinese for all explanatory string values. Keep JSON keys in English."
        if language == "zh"
        else "Use English for all explanatory string values."
    )
    return f"""
You are building a war-gaming forecast for the Iran theater.

Rules:
- Output one JSON object only.
- Follow the schema shape below.
- Treat everything as uncertain scenario analysis, not fact.
- Do not claim certainty on named successors.
- {natural_language_rule}
- You are not a news reader here. You are reading a structured state package.
- Use probabilities that sum to 1.0 across outcome_probabilities.
- Each outcome_probabilities entry must include scenario, probability, and rationale.
- Successor scenarios must each include name, probability, trigger_conditions,
  lead_figures as an array of strings, institutional_architecture, and
  first_180_day_policies as an array of strings.
- Date fields must be ISO 8601 or YYYY-MM-DD.
- Use only the supplied top events, 3 core signals, signal evidence, market signals, contradictions, and trend summary.
- Do not invent additional raw-source claims outside the package.

Schema:
{schema}

Required output intent:
- Use the 3 core signals as the main causal frame: military capability, war cost, and negotiation signals.
- Predict war termination windows: p10, p50, p90
- Rank likely end states
- Estimate plausible successor government scenarios if regime transition occurs
- For each successor scenario, state likely coalition form, top figures, governing structure,
  and first-180-day policy direction
- Include assumptions and uncertainty drivers
- Give extra weight to decisive signals and contradictions
- Use indicator_evidence to see which of the 3 core signals are actually supported by current evidence, and which remain thin
- When market signals are present, use oil-price moves and prediction-market probabilities as auxiliary evidence, not as standalone truth

Structured analysis package:
{payload}
""".strip()


def normalize_forecast(forecast: Dict[str, Any]) -> Dict[str, Any]:
    outcomes = forecast.get("outcome_probabilities", [])
    total = 0.0
    cleaned = []
    for index, outcome in enumerate(outcomes, start=1):
        probability = float(outcome.get("probability", 0.0))
        if probability < 0:
            probability = 0.0
        scenario_name = outcome.get("scenario") or outcome.get("name") or f"scenario_{index}"
        rationale = outcome.get("rationale") or outcome.get("description", "")
        cleaned.append(
            {
                **outcome,
                "scenario": scenario_name,
                "rationale": rationale,
                "probability": probability,
            }
        )
        total += probability
    if cleaned and total > 0:
        for outcome in cleaned:
            outcome["probability"] = round(outcome["probability"] / total, 4)
    forecast["outcome_probabilities"] = cleaned
    successor_scenarios = []
    for index, scenario in enumerate(
        forecast.get("successor_government_scenarios", []),
        start=1,
    ):
        name = scenario.get("name") or f"successor_scenario_{index}"
        lead_figures = scenario.get("lead_figures", [])
        if isinstance(lead_figures, str):
            lead_figures = [lead_figures]
        policies = scenario.get("first_180_day_policies", [])
        if isinstance(policies, str):
            policies = [policies]
        successor_scenarios.append(
            {
                **scenario,
                "name": name,
                "lead_figures": lead_figures,
                "first_180_day_policies": policies,
            }
        )
    forecast["successor_government_scenarios"] = successor_scenarios
    return forecast


def generate_forecast(
    summary: Dict[str, Any],
    model: Optional[str] = None,
    language: str = "zh",
) -> Dict[str, Any]:
    prompt = build_prompt(summary, language=language)
    forecast = run_structured_prompt(prompt, model=model)
    forecast = normalize_forecast(forecast)
    forecast.setdefault("forecast_id", str(uuid4()))
    return forecast
