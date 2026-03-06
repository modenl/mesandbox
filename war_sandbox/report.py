import json
from typing import Any, Dict


TEXT = {
    "zh": {
        "title": "# 伊朗战局沙盘推演报告",
        "as_of": "截至",
        "evidence_items": "证据条目",
        "tension_index": "紧张指数",
        "decision_panel": "终局面板",
        "state_variables": "7个状态变量",
        "top_signals": "前5个决定性信号",
        "uncertainty": "最大不确定性",
        "war_end_window": "战争结束时间窗",
        "rationale": "依据",
        "outcomes": "结果概率",
        "successors": "继任政府场景",
        "watch": "重点观察指标",
        "confidence": "置信说明",
        "assumptions": "前提假设",
        "evidence": "证据",
    },
    "en": {
        "title": "# Iran War Sandbox Forecast",
        "as_of": "As of",
        "evidence_items": "Evidence items",
        "tension_index": "Tension index",
        "decision_panel": "Endgame Panel",
        "state_variables": "7 State Variables",
        "top_signals": "Top 5 Decisive Signals",
        "uncertainty": "Biggest Uncertainty",
        "war_end_window": "War End Window",
        "rationale": "Rationale",
        "outcomes": "Outcome Probabilities",
        "successors": "Successor Government Scenarios",
        "watch": "Watch Indicators",
        "confidence": "Confidence",
        "assumptions": "Assumptions",
        "evidence": "Evidence",
    },
}


def render_markdown(summary: Dict[str, Any], forecast: Dict[str, Any], language: str = "zh") -> str:
    text = TEXT.get(language, TEXT["zh"])
    lines = []
    lines.append(text["title"])
    lines.append("")
    lines.append(f"- {text['as_of']}: {forecast.get('forecast_as_of', summary.get('generated_at'))}")
    lines.append(f"- {text['evidence_items']}: {summary.get('item_count', 0)}")
    lines.append(f"- {text['tension_index']}: {summary.get('tension_index', 'n/a')}")
    lines.append("")
    decision_panel = summary.get("decision_panel", {})
    if decision_panel:
        lines.append(f"## {text['decision_panel']}")
        lines.append(f"- {decision_panel.get('current_state', 'n/a')}")
        lines.append(f"- {decision_panel.get('most_likely_outcome', 'n/a')}")
        for window in decision_panel.get("end_windows", []):
            lines.append(f"  - {window.get('window_days', 'n/a')}d: {window.get('probability', 'n/a')}")
        lines.append("")
    state_variables = summary.get("state_variables", [])
    if state_variables:
        lines.append(f"## {text['state_variables']}")
        for item in state_variables:
            lines.append(
                f"- {item.get('label', item.get('id', 'unknown'))}: {item.get('value', 'n/a')} ({item.get('direction', 'n/a')})"
            )
        lines.append("")
    top_signals = decision_panel.get("top_decisive_signals", [])
    if top_signals:
        lines.append(f"## {text['top_signals']}")
        for item in top_signals:
            lines.append(
                f"- {item.get('title', 'n/a')} | source={item.get('source', 'n/a')} | credibility={item.get('credibility', 'n/a')} | importance={item.get('importance', 'n/a')}"
            )
        lines.append("")
    uncertainties = decision_panel.get("max_uncertainty", [])
    if uncertainties:
        lines.append(f"## {text['uncertainty']}")
        for item in uncertainties:
            lines.append(f"- {item}")
        lines.append("")
    lines.append(f"## {text['war_end_window']}")
    window = forecast.get("war_end_window", {})
    lines.append(f"- P10: {window.get('p10', 'n/a')}")
    lines.append(f"- P50: {window.get('p50', 'n/a')}")
    lines.append(f"- P90: {window.get('p90', 'n/a')}")
    lines.append(f"- {text['rationale']}: {window.get('rationale', 'n/a')}")
    lines.append("")
    lines.append(f"## {text['outcomes']}")
    for outcome in forecast.get("outcome_probabilities", []):
        lines.append(
            f"- {outcome.get('scenario', 'unknown')}: {outcome.get('probability', 0)}"
            f" | {text['rationale'].lower()}: {outcome.get('rationale', '')}"
        )
    lines.append("")
    lines.append(f"## {text['successors']}")
    for scenario in forecast.get("successor_government_scenarios", []):
        lines.append(
            f"- {scenario.get('name', 'unnamed')}: {scenario.get('probability', 0)}"
        )
        lines.append(
            f"  trigger={scenario.get('trigger_conditions', '')}; "
            f"lead_figures={json.dumps(scenario.get('lead_figures', []), ensure_ascii=False)}; "
            f"architecture={scenario.get('institutional_architecture', '')}; "
            f"policies={json.dumps(scenario.get('first_180_day_policies', []), ensure_ascii=False)}"
        )
    lines.append("")
    lines.append(f"## {text['watch']}")
    for indicator in forecast.get("key_indicators_to_watch", []):
        lines.append(f"- {indicator}")
    lines.append("")
    lines.append(f"## {text['confidence']}")
    lines.append(forecast.get("confidence_note", "n/a"))
    lines.append("")
    lines.append(f"## {text['assumptions']}")
    for item in forecast.get("assumptions", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"## {text['evidence']}")
    for item in forecast.get("evidence", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def categorical_brier(outcomes: list[dict[str, Any]], resolved: str) -> float:
    score = 0.0
    for outcome in outcomes:
        p = float(outcome.get("probability", 0.0))
        o = 1.0 if outcome.get("scenario") == resolved else 0.0
        score += (p - o) ** 2
    return round(score, 6)
