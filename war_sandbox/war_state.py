from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .gemini_runner import translate_news_titles


SOURCE_STACK = [
    {"id": "gdelt_articles", "name": "GDELT Article List RSS", "kind": "gdelt"},
    {"id": "gdelt_timeline", "name": "GDELT Event / GKG Pulse", "kind": "gdelt"},
    {"id": "google_news_iran_conflict", "name": "Google News Iran Conflict", "kind": "aggregator"},
    {"id": "centcom_dvids", "name": "CENTCOM Press Releases", "kind": "official"},
    {"id": "idf_releases", "name": "IDF Media Releases", "kind": "official"},
    {"id": "presstv_latest", "name": "PressTV Latest", "kind": "official"},
    {"id": "radiofarda_iran", "name": "Radio Farda Iran News", "kind": "wire"},
    {"id": "unnews_middle_east", "name": "UN News Middle East", "kind": "official"},
    {"id": "unnews_peace_security", "name": "UN News Peace and Security", "kind": "official"},
    {"id": "iaea_news", "name": "IAEA News", "kind": "official"},
    {"id": "adsb_military", "name": "ADSB.lol", "kind": "sensor"},
    {"id": "nasa_firms", "name": "NASA FIRMS", "kind": "sensor"},
    {"id": "acled_calibration", "name": "ACLED", "kind": "geo"},
]


SOURCE_CREDIBILITY = {
    "sensor": 0.95,
    "official": 0.82,
    "wire": 0.75,
    "geo": 0.62,
    "aggregator": 0.52,
    "unknown": 0.4,
}


VARIABLES = [
    {
        "id": "missile_drone_capacity",
        "label_zh": "导弹与无人机持续打击能力",
        "label_en": "Missile and drone strike persistence",
        "up_terms": ["missile", "drone", "launch", "salvo", "barrage", "retaliation"],
        "down_terms": ["destroyed", "intercepted", "air defense", "degraded", "struck launcher"],
    },
    {
        "id": "underground_systems",
        "label_zh": "地下发射/储存体系是否还在",
        "label_en": "Underground launch/storage system survivability",
        "up_terms": ["tunnel", "underground", "silo", "bunker", "missile base"],
        "down_terms": ["bunker buster", "collapsed", "penetrated", "destroyed base", "struck tunnel"],
    },
    {
        "id": "hormuz_shipping",
        "label_zh": "霍尔木兹与海运是否恢复",
        "label_en": "Hormuz and commercial shipping recovery",
        "up_terms": ["tanker", "shipping", "hormuz", "vessel", "oil terminal", "port"],
        "down_terms": ["reopened", "resumed shipping", "partial transit", "traffic restored"],
    },
    {
        "id": "new_state_involvement",
        "label_zh": "是否有新国家被卷入",
        "label_en": "Whether new states are being drawn in",
        "up_terms": ["u.s.", "united states", "gulf state", "saudi", "uae", "qatar", "iraq", "syria", "hezbollah"],
        "down_terms": ["no wider war", "contained", "limited objectives"],
    },
    {
        "id": "us_objective_expansion",
        "label_zh": "美方目标是否扩大",
        "label_en": "Whether U.S. objectives are expanding",
        "up_terms": ["regime change", "leadership", "expanded target", "command and control", "next phase"],
        "down_terms": ["limited objectives", "not expanding", "missile only", "no occupation"],
    },
    {
        "id": "command_chain_stability",
        "label_zh": "伊朗最高层与指挥链是否稳定",
        "label_en": "Iranian leadership and command-chain stability",
        "up_terms": ["supreme leader", "irgc", "command chain", "stability", "consolidated"],
        "down_terms": ["coup", "succession", "defection", "fracture", "leadership crisis"],
    },
    {
        "id": "domestic_instability_talks",
        "label_zh": "国内失稳、倒戈、接班与谈判迹象",
        "label_en": "Domestic instability, defections, succession, and talks",
        "up_terms": ["protest", "strike", "ceasefire", "talks", "mediation", "defection", "transition"],
        "down_terms": ["crackdown restored order", "no talks", "unity"],
    },
]


STRATEGIC_TERMS = [
    "missile base",
    "launcher",
    "port",
    "oil depot",
    "command center",
    "air defense",
    "naval",
    "hormuz",
    "nuclear",
    "succession",
    "war powers",
    "congress",
    "hotspot",
    "airstrike",
    "military flight",
    "air refueling",
    "awacs",
]

IRAN_CONTEXT_TERMS = [
    "iran",
    "tehran",
    "irgc",
    "israel",
    "hormuz",
    "persian gulf",
    "gulf",
    "beirut",
    "lebanon",
    "iraq",
    "syria",
    "u.s.",
    "united states",
    "centcom",
]

CONFLICT_TERMS = [
    "missile",
    "drone",
    "strike",
    "airstrike",
    "attack",
    "war",
    "ceasefire",
    "bomber",
    "intercept",
    "naval",
    "military",
    "base",
    "launcher",
    "tanker",
    "air defense",
]


DISPLAY_THRESHOLD = {"credibility": 0.62, "importance": 0.68}


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = str(value).strip()
    for normalized in (value.replace("Z", "+00:00"), value):
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _count_term_hits(text: str, terms: List[str]) -> int:
    hits = 0
    for term in terms:
        normalized = term.lower()
        if re.fullmatch(r"[a-z0-9 ]+", normalized):
            if re.search(rf"\b{re.escape(normalized)}\b", text):
                hits += 1
        elif normalized in text:
            hits += 1
    return hits


def _normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def classify_source(item: Dict[str, Any]) -> str:
    source = str(item.get("source", "")).lower()
    title = str(item.get("title", "")).lower()
    url = str(item.get("url", "")).lower()
    domain = urlparse(url).netloc.lower()

    if source.startswith("gdelt"):
        return "wire"
    if "liveuamap" in source or "liveuamap" in url:
        return "geo"
    if "iaea" in source or "iaea.org" in domain or "un.org" in domain:
        return "official"
    if any(token in source for token in ["centcom", "idf", "irna", "tasnim", "presstv"]):
        return "official"
    if any(token in domain for token in ["centcom", "dvidshub", "idf", "irna", "tasnim", "presstv"]):
        return "official"
    if "radiofarda" in source or "radiofarda" in domain:
        return "wire"
    if any(token in title for token in ["reuters", "ap ", "associated press", "bbc"]):
        return "wire"
    if any(token in source for token in ["adsb", "firms", "vesselfinder"]):
        return "sensor"
    if source.startswith("acled"):
        return "geo"
    if any(token in domain for token in ["adsb", "vesselfinder", "firms", "nasa"]):
        return "sensor"
    if source.startswith("rss:"):
        return "aggregator"
    return "unknown"


def score_credibility(item: Dict[str, Any]) -> float:
    bucket = classify_source(item)
    return SOURCE_CREDIBILITY.get(bucket, SOURCE_CREDIBILITY["unknown"])


def score_importance(item: Dict[str, Any]) -> float:
    text = " ".join(
        filter(
            None,
            [str(item.get("title", "")), str(item.get("content_text", "")), str(item.get("url", ""))],
        )
    ).lower()
    strategic_hits = _count_term_hits(text, STRATEGIC_TERMS)
    context_hits = _count_term_hits(text, IRAN_CONTEXT_TERMS)
    conflict_hits = _count_term_hits(text, CONFLICT_TERMS)
    variable_hits = 0
    for variable in VARIABLES:
        variable_hits += _count_term_hits(text, variable["up_terms"])
        variable_hits += _count_term_hits(text, variable["down_terms"])
    official_bonus = 1 if classify_source(item) in {"sensor", "official", "wire"} else 0
    raw = 0.45 * min(strategic_hits / 2.0, 1.0) + 0.35 * min(variable_hits / 3.0, 1.0) + 0.20 * official_bonus
    if not context_hits or not conflict_hits:
        raw *= 0.25
    elif context_hits == 1 and conflict_hits == 1:
        raw *= 0.8
    return round(_clamp(raw), 4)


def map_event_to_variables(item: Dict[str, Any]) -> Dict[str, float]:
    text = " ".join(
        filter(
            None,
            [str(item.get("title", "")), str(item.get("content_text", "")), str(item.get("url", ""))],
        )
    ).lower()
    result = {}
    for variable in VARIABLES:
        up = _count_term_hits(text, variable["up_terms"])
        down = _count_term_hits(text, variable["down_terms"])
        if up or down:
            result[variable["id"]] = float(up - down)
    return result


def build_signal_events(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in items:
        credibility = score_credibility(item)
        importance = score_importance(item)
        variable_impacts = map_event_to_variables(item)
        combined = round(0.55 * credibility + 0.45 * importance, 4)
        display = credibility >= DISPLAY_THRESHOLD["credibility"] and importance >= DISPLAY_THRESHOLD["importance"]
        event = {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published_at": item.get("published_at"),
            "credibility": credibility,
            "importance": importance,
            "combined": combined,
            "display": display,
            "variable_impacts": variable_impacts,
            "duplicate_count": 1,
        }
        key = (
            str(event["source"]).lower(),
            _normalized_title(str(event["title"])),
        )
        existing = deduped.get(key)
        if not existing:
            deduped[key] = event
            continue
        existing["duplicate_count"] += 1
        if combined > existing["combined"]:
            event["duplicate_count"] = existing["duplicate_count"]
            deduped[key] = event
        else:
            existing["duplicate_count"] = max(existing["duplicate_count"], event["duplicate_count"])
            if event.get("published_at") and (
                not existing.get("published_at") or str(event["published_at"]) > str(existing["published_at"])
            ):
                existing["published_at"] = event["published_at"]
            for variable_id, impact in variable_impacts.items():
                current = existing["variable_impacts"].get(variable_id, 0.0)
                if abs(impact) > abs(current):
                    existing["variable_impacts"][variable_id] = impact
    events = list(deduped.values())
    events.sort(
        key=lambda event: (
            event["display"],
            event["importance"],
            event["combined"],
            event.get("duplicate_count", 1),
        ),
        reverse=True,
    )
    return events


def select_diverse_events(events: List[Dict[str, Any]], limit: int = 20, per_source_cap: int = 2) -> List[Dict[str, Any]]:
    selected = []
    source_counts: Dict[str, int] = {}
    for event in events:
        source = str(event.get("source", ""))
        if source_counts.get(source, 0) >= per_source_cap:
            continue
        selected.append(event)
        source_counts[source] = source_counts.get(source, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def compute_state_variables(events: List[Dict[str, Any]], language: str) -> List[Dict[str, Any]]:
    labels_key = "label_zh" if language == "zh" else "label_en"
    states = []
    for variable in VARIABLES:
        total = 0.0
        support = 0.0
        decisive = []
        for event in events:
            impact = event["variable_impacts"].get(variable["id"], 0.0)
            if not impact:
                continue
            weight = event["combined"]
            total += impact * weight
            support += abs(weight)
            decisive.append(event)
        normalized = 50.0 + 22.0 * total
        value = round(max(0.0, min(100.0, normalized)), 1)
        direction = "up" if total > 0.18 else "down" if total < -0.18 else "flat"
        states.append(
            {
                "id": variable["id"],
                "label": variable[labels_key],
                "value": value,
                "direction": direction,
                "evidence_count": len(decisive),
                "decisive_events": [event["title"] for event in decisive[:3]],
            }
        )
    return states


def derive_current_state(state_variables: Dict[str, Dict[str, Any]], language: str) -> str:
    shipping = state_variables["hormuz_shipping"]["value"]
    involvement = state_variables["new_state_involvement"]["value"]
    talks = state_variables["domestic_instability_talks"]["value"]
    expansion = state_variables["us_objective_expansion"]["value"]
    missile = state_variables["missile_drone_capacity"]["value"]
    if involvement >= 65 or shipping >= 72:
        return "地区外溢" if language == "zh" else "Regional Spillover"
    if talks >= 62 and expansion <= 48 and missile <= 52:
        return "谈判前夜" if language == "zh" else "Pre-Negotiation"
    if expansion >= 58 or missile >= 60:
        return "扩大战" if language == "zh" else "Expansion Phase"
    return "压制战" if language == "zh" else "Containment / Suppression"


def termination_windows(state_variables: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    missile = state_variables["missile_drone_capacity"]["value"] / 100.0
    underground = state_variables["underground_systems"]["value"] / 100.0
    shipping = state_variables["hormuz_shipping"]["value"] / 100.0
    involvement = state_variables["new_state_involvement"]["value"] / 100.0
    expansion = state_variables["us_objective_expansion"]["value"] / 100.0
    leadership = state_variables["command_chain_stability"]["value"] / 100.0
    talks = state_variables["domestic_instability_talks"]["value"] / 100.0

    fast = _clamp(0.35 * (1 - missile) + 0.20 * (1 - underground) + 0.20 * talks + 0.15 * (1 - expansion) + 0.10 * (1 - shipping))
    mid = _clamp(0.30 * (1 - underground) + 0.20 * talks + 0.20 * (1 - involvement) + 0.15 * (1 - expansion) + 0.15 * (1 - leadership))
    slow = _clamp(0.35 * involvement + 0.25 * shipping + 0.20 * expansion + 0.20 * missile)

    return [
        {"window_days": 7, "probability": round(0.10 + 0.25 * fast, 4)},
        {"window_days": 14, "probability": round(0.18 + 0.32 * mid, 4)},
        {"window_days": 30, "probability": round(0.28 + 0.38 * (0.5 * fast + 0.5 * mid), 4)},
        {"window_days": 60, "probability": round(0.50 + 0.35 * (1 - slow), 4)},
    ]


def derive_outcome(state_variables: Dict[str, Dict[str, Any]], language: str) -> Dict[str, Any]:
    talks = state_variables["domestic_instability_talks"]["value"]
    involvement = state_variables["new_state_involvement"]["value"]
    expansion = state_variables["us_objective_expansion"]["value"]
    leadership = state_variables["command_chain_stability"]["value"]

    candidates = []
    candidates.append(
        (
            "停火" if language == "zh" else "Ceasefire",
            0.45 * (talks / 100.0) + 0.25 * (1 - involvement / 100.0) + 0.30 * (1 - expansion / 100.0),
        )
    )
    candidates.append(
        (
            "冻结冲突" if language == "zh" else "Frozen Conflict",
            0.45 * (involvement / 100.0) + 0.25 * (leadership / 100.0) + 0.30 * (1 - talks / 100.0),
        )
    )
    candidates.append(
        (
            "政权裂变" if language == "zh" else "Regime Fracture",
            0.55 * (1 - leadership / 100.0) + 0.25 * (talks / 100.0) + 0.20 * (expansion / 100.0),
        )
    )
    candidates.append(
        (
            "地区扩大战" if language == "zh" else "Regional Expansion",
            0.55 * (involvement / 100.0) + 0.25 * (expansion / 100.0) + 0.20 * (1 - talks / 100.0),
        )
    )
    outcome, score = max(candidates, key=lambda pair: pair[1])
    return {"label": outcome, "score": round(score, 4)}


def build_uncertainties(events: List[Dict[str, Any]], state_variables: Dict[str, Dict[str, Any]], language: str) -> List[str]:
    uncertainties = []
    if state_variables["domestic_instability_talks"]["value"] >= 58 and state_variables["missile_drone_capacity"]["value"] >= 55:
        uncertainties.append(
            "谈判信号与持续发射能力并存，说明伊朗可能一边试探斡旋，一边保留升级筹码。"
            if language == "zh"
            else "Negotiation signals coexist with sustained strike capacity, suggesting Iran may preserve escalation leverage while probing for talks."
        )
    if state_variables["us_objective_expansion"]["value"] <= 45 and state_variables["new_state_involvement"]["value"] >= 60:
        uncertainties.append(
            "美方口径仍称目标有限，但地区卷入度在上升，存在行动意图与外溢后果不一致的风险。"
            if language == "zh"
            else "U.S. rhetoric remains limited while regional involvement rises, creating a mismatch risk between stated goals and spillover effects."
        )
    top_hidden = [event for event in events if not event["display"]][:2]
    for event in top_hidden:
        uncertainties.append(
            (
                "高噪声但未被上屏的信号："
                if language == "zh"
                else "Suppressed but potentially relevant signal: "
            )
            + event["title"]
        )
    return uncertainties[:2]


def build_analysis_package(
    items: List[Dict[str, Any]],
    language: str,
) -> Dict[str, Any]:
    events = build_signal_events(items)
    displayed_events = [event for event in events if event["display"]]
    ranked_events = displayed_events or events
    analysis_events = select_diverse_events(ranked_events, limit=20, per_source_cap=2)
    display_events = select_diverse_events(ranked_events, limit=50, per_source_cap=4)
    state_list = compute_state_variables(analysis_events, language)
    state_map = {state["id"]: state for state in state_list}
    windows = termination_windows(state_map)
    outcome = derive_outcome(state_map, language)
    phase = derive_current_state(state_map, language)
    decisive = analysis_events[:5]
    uncertainties = build_uncertainties(analysis_events, state_map, language)
    contradictions = [
        uncertainty for uncertainty in uncertainties
    ][:3]

    source_mix: Dict[str, int] = {}
    for item in items:
        source_mix[item["source"]] = source_mix.get(item["source"], 0) + 1

    latest_ts = None
    for item in items:
        parsed = _parse_timestamp(item.get("published_at"))
        if parsed and (latest_ts is None or parsed > latest_ts):
            latest_ts = parsed

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "item_count": len(items),
        "source_mix": source_mix,
        "tension_index": round(
            _clamp(
                (
                    state_map["missile_drone_capacity"]["value"]
                    + state_map["new_state_involvement"]["value"]
                    + state_map["us_objective_expansion"]["value"]
                )
                / 300.0
            )
            * 100.0,
            1,
        ),
        "state_variables": state_list,
        "top_events": display_events,
        "all_scored_events": select_diverse_events(events, limit=50, per_source_cap=4),
        "contradictions": contradictions,
        "decision_panel": {
            "current_state": phase,
            "end_windows": windows,
            "most_likely_outcome": outcome["label"],
            "top_decisive_signals": [
                {
                    "title": event["title"],
                    "source": event["source"],
                    "credibility": event["credibility"],
                    "importance": event["importance"],
                }
                for event in decisive
            ],
            "max_uncertainty": uncertainties[:2],
        },
        "trend_summary": {
            "latest_event_at": latest_ts.isoformat() if latest_ts else None,
            "recent_signal_share": round(
                _safe_ratio(
                    sum(
                        1
                        for event in analysis_events
                        if (parsed := _parse_timestamp(event.get("published_at")))
                        and parsed >= datetime.now(timezone.utc) - timedelta(hours=24)
                    ),
                    len(analysis_events),
                ),
                4,
            ),
        },
        "source_stack": SOURCE_STACK,
        "summary_language": "raw",
    }


def localize_summary(summary: Dict[str, Any], language: str, model: Optional[str] = None) -> Dict[str, Any]:
    if not summary:
        return summary
    localized = {
        **summary,
        "top_events": [dict(item) for item in summary.get("top_events", [])],
        "all_scored_events": [dict(item) for item in summary.get("all_scored_events", [])],
        "decision_panel": {
            **summary.get("decision_panel", {}),
            "top_decisive_signals": [dict(item) for item in summary.get("decision_panel", {}).get("top_decisive_signals", [])],
        },
    }
    titles = [str(item.get("title", "")) for item in localized.get("top_events", [])]
    if not titles:
        localized["summary_language"] = language
        return localized

    translated = translate_news_titles(titles, language=language, model=model)
    for item, translated_title in zip(localized["top_events"], translated):
        item.setdefault("title_original", item.get("title", ""))
        item["title"] = translated_title

    decisive = localized.get("decision_panel", {}).get("top_decisive_signals", [])
    for item, translated_title in zip(decisive, translated):
        item.setdefault("title_original", item.get("title", ""))
        item["title"] = translated_title

    localized["summary_language"] = language
    return localized
