from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .gemini_runner import assess_event_relevance, stabilize_event_summary, translate_brief_texts, translate_news_titles


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
    {"id": "oil_market", "name": "International Crude Oil", "kind": "market"},
    {"id": "polymarket_geopolitics", "name": "Polymarket Geopolitical Markets", "kind": "market"},
    {"id": "nasa_firms", "name": "NASA FIRMS", "kind": "sensor"},
    {"id": "acled_calibration", "name": "ACLED", "kind": "geo"},
]


SOURCE_CREDIBILITY = {
    "sensor": 0.95,
    "market": 0.84,
    "official": 0.82,
    "wire": 0.75,
    "geo": 0.62,
    "aggregator": 0.52,
    "unknown": 0.4,
}


VARIABLES = [
    {
        "id": "strike_capacity",
        "group_zh": "军事能力",
        "group_en": "Military Capability",
        "label_zh": "打击能力",
        "label_en": "Strike capacity",
        "up_terms": ["missile", "drone", "launch", "salvo", "barrage", "precision strike", "rocket force", "retaliation"],
        "down_terms": ["launcher destroyed", "stockpile depleted", "factory hit", "production hit", "degraded", "suppressed"],
    },
    {
        "id": "logistics_capacity",
        "group_zh": "军事能力",
        "group_en": "Military Capability",
        "label_zh": "后勤能力",
        "label_en": "Logistics capacity",
        "up_terms": ["fuel", "ammunition", "resupply", "transport corridor", "air bridge", "sealift", "logistics", "port operations", "airport operations"],
        "down_terms": ["fuel shortage", "ammo shortage", "supply disruption", "port closed", "runway damaged", "convoy hit", "resupply halted", "bottleneck"],
    },
    {
        "id": "command_control",
        "group_zh": "军事能力",
        "group_en": "Military Capability",
        "label_zh": "指挥与控制（C2）",
        "label_en": "Command and control",
        "up_terms": ["command center", "communications restored", "radar active", "satellite link", "c2", "integrated air defense", "coordination"],
        "down_terms": ["communications outage", "command center hit", "radar destroyed", "jammed", "c2 disrupted", "cyberattack", "leadership bunker hit"],
    },
    {
        "id": "operational_control",
        "group_zh": "军事能力",
        "group_en": "Military Capability",
        "label_zh": "战场控制",
        "label_en": "Operational control",
        "up_terms": ["air superiority", "air dominance", "sea control", "maritime control", "secured corridor", "held territory", "intercepts successful"],
        "down_terms": ["lost airspace", "air defense overwhelmed", "retreat", "withdrawal", "port shut", "ship hit", "lost control"],
    },
    {
        "id": "leadership_stability",
        "group_zh": "政治稳定",
        "group_en": "Political Stability",
        "label_zh": "领导层稳定",
        "label_en": "Leadership stability",
        "up_terms": ["supreme leader statement", "cabinet unity", "chain of command intact", "leadership stable", "succession settled"],
        "down_terms": ["succession", "leadership crisis", "power struggle", "rumors of death", "assassinated", "interim leader"],
    },
    {
        "id": "domestic_support",
        "group_zh": "政治稳定",
        "group_en": "Political Stability",
        "label_zh": "国内支持度",
        "label_en": "Domestic support",
        "up_terms": ["rally", "mobilization support", "public support", "national unity", "state media support"],
        "down_terms": ["protest", "strike", "unrest", "anti-war", "panic buying", "civilian anger", "funeral unrest"],
    },
    {
        "id": "elite_cohesion",
        "group_zh": "政治稳定",
        "group_en": "Political Stability",
        "label_zh": "精英联盟稳定",
        "label_en": "Elite cohesion",
        "up_terms": ["irgc loyalty", "army loyalty", "security services united", "clerical backing", "elite unity"],
        "down_terms": ["defection", "purge", "elite split", "commander removed", "resignation", "mutiny", "factional"],
    },
    {
        "id": "economic_resilience",
        "group_zh": "经济与资源",
        "group_en": "Economy and Resources",
        "label_zh": "经济承受能力",
        "label_en": "Economic resilience",
        "up_terms": ["fx reserves", "stabilized currency", "budget cushion", "subsidy support", "economic resilience"],
        "down_terms": ["inflation", "currency collapse", "recession", "bank stress", "budget deficit", "shortage", "capital flight"],
    },
    {
        "id": "energy_trade_disruption",
        "group_zh": "经济与资源",
        "group_en": "Economy and Resources",
        "label_zh": "能源与贸易受扰",
        "label_en": "Energy and trade disruption",
        "up_terms": ["hormuz", "tanker", "shipping", "oil price", "brent", "wti", "port closed", "export halted", "insurance spike", "terminal hit"],
        "down_terms": ["shipping resumed", "transit restored", "exports resumed", "port reopened", "insurance normalized"],
    },
    {
        "id": "sanctions_pressure",
        "group_zh": "经济与资源",
        "group_en": "Economy and Resources",
        "label_zh": "制裁压力",
        "label_en": "Sanctions pressure",
        "up_terms": ["sanctions", "asset freeze", "secondary sanctions", "technology ban", "financial restrictions", "export controls"],
        "down_terms": ["sanctions eased", "waiver", "relief", "trade channel reopened", "unfroze"],
    },
    {
        "id": "external_involvement",
        "group_zh": "国际环境",
        "group_en": "International Environment",
        "label_zh": "外部国家介入",
        "label_en": "External state involvement",
        "up_terms": ["u.s.", "united states", "centcom", "uk", "france", "saudi", "uae", "qatar", "iraq", "syria", "hezbollah", "russia", "china", "coalition", "carrier group"],
        "down_terms": ["no wider war", "staying out", "neutral", "won't join", "non-intervention"],
    },
    {
        "id": "negotiation_signals",
        "group_zh": "国际环境",
        "group_en": "International Environment",
        "label_zh": "谈判信号",
        "label_en": "Negotiation signals",
        "up_terms": ["ceasefire", "talks", "mediation", "backchannel", "envoy", "qatar mediation", "oman mediation", "truce", "proposal", "delegation"],
        "down_terms": ["talks rejected", "no ceasefire", "negotiations failed", "walked away", "maximalist"],
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
    "crude oil",
    "brent",
    "wti",
    "oil price",
    "prediction market",
    "netanyahu",
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
    "netanyahu",
    "israeli",
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
    "prime minister",
    "resign",
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


def _looks_localized(text: str, language: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", value))
    if language == "zh":
        return has_cjk
    return not has_cjk


def _event_sort_key(event: Dict[str, Any]) -> datetime:
    return _parse_timestamp(event.get("published_at")) or _parse_timestamp(event.get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc)


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


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    if any(token in source for token in ["oil_market", "polymarket"]):
        return "market"
    if source.startswith("acled"):
        return "geo"
    if any(token in domain for token in ["adsb", "vesselfinder", "firms", "nasa"]):
        return "sensor"
    if source.startswith("rss:"):
        return "aggregator"
    return "unknown"


def score_credibility(item: Dict[str, Any]) -> float:
    source = str(item.get("source", "")).lower()
    if "oil_market" in source:
        return 0.9
    if "polymarket" in source:
        return 0.78
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
    payload = item.get("payload") or {}
    variable_hits = 0
    for variable in VARIABLES:
        variable_hits += _count_term_hits(text, variable["up_terms"])
        variable_hits += _count_term_hits(text, variable["down_terms"])
    official_bonus = 1 if classify_source(item) in {"sensor", "official", "wire"} else 0
    market_bonus = 1 if classify_source(item) == "market" else 0
    market_strength = 0.0
    source_name = str(item.get("source", "")).lower()
    if source_name == "polymarket_geopolitics":
        volume = _safe_float(payload.get("volume"))
        volume_24h = _safe_float(payload.get("volume24hr"))
        liquidity = _safe_float(payload.get("liquidity"))
        market_strength = _clamp(
            0.50 * min(volume_24h / 250000.0, 1.0)
            + 0.30 * min(volume / 1000000.0, 1.0)
            + 0.20 * min(liquidity / 100000.0, 1.0)
        )
    elif source_name == "oil_market":
        price = _safe_float((payload.get("meta") or {}).get("regularMarketPrice"))
        previous_close = _safe_float((payload.get("meta") or {}).get("previousClose") or (payload.get("meta") or {}).get("chartPreviousClose"))
        change_pct = abs((price - previous_close) / previous_close * 100.0) if previous_close else 0.0
        market_strength = min(change_pct / 8.0, 1.0)
    raw = (
        0.40 * min(strategic_hits / 2.0, 1.0)
        + 0.30 * min(variable_hits / 3.0, 1.0)
        + 0.20 * official_bonus
        + 0.10 * market_bonus
        + 0.20 * market_strength
    )
    if market_bonus and strategic_hits:
        if not context_hits and not conflict_hits:
            raw *= 0.85
    elif not context_hits or not conflict_hits:
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
            "content_text": str(item.get("content_text", ""))[:1000],
            "credibility": credibility,
            "importance": importance,
            "combined": combined,
            "display": display,
            "variable_impacts": variable_impacts,
            "duplicate_count": 1,
            "market_volume": _safe_float((item.get("payload") or {}).get("volume")),
            "market_volume_24h": _safe_float((item.get("payload") or {}).get("volume24hr")),
            "market_liquidity": _safe_float((item.get("payload") or {}).get("liquidity")),
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
    group_key = "group_zh" if language == "zh" else "group_en"
    states = []
    for variable in VARIABLES:
        total = 0.0
        decisive = []
        for event in events:
            impact = event["variable_impacts"].get(variable["id"], 0.0)
            if not impact:
                continue
            weight = event["combined"]
            total += impact * weight
            decisive.append(event)
        normalized = 50.0 + 22.0 * total
        value = round(max(0.0, min(100.0, normalized)), 1)
        direction = "up" if total > 0.18 else "down" if total < -0.18 else "flat"
        states.append(
            {
                "id": variable["id"],
                "group": variable[group_key],
                "label": variable[labels_key],
                "value": value,
                "direction": direction,
                "evidence_count": len(decisive),
                "decisive_events": [event["title"] for event in decisive[:3]],
            }
        )
    return states


def group_state_variables(state_variables: List[Dict[str, Any]], language: str) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for item in state_variables:
        group = str(item.get("group") or ("Other" if language == "en" else "其他"))
        bucket = groups.setdefault(group, {"group": group, "items": [], "value_sum": 0.0})
        bucket["items"].append(item)
        bucket["value_sum"] += float(item.get("value", 0.0) or 0.0)
    ordered_labels = [
        "军事能力" if language == "zh" else "Military Capability",
        "政治稳定" if language == "zh" else "Political Stability",
        "经济与资源" if language == "zh" else "Economy and Resources",
        "国际环境" if language == "zh" else "International Environment",
    ]
    ordered = []
    for label in ordered_labels:
        bucket = groups.get(label)
        if not bucket:
            continue
        ordered.append(
            {
                "group": label,
                "value": round(bucket["value_sum"] / max(len(bucket["items"]), 1), 1),
                "items": bucket["items"],
            }
        )
    for label, bucket in groups.items():
        if label in ordered_labels:
            continue
        ordered.append(
            {
                "group": label,
                "value": round(bucket["value_sum"] / max(len(bucket["items"]), 1), 1),
                "items": bucket["items"],
            }
        )
    return ordered


def _state_value(state_variables: Dict[str, Dict[str, Any]], state_id: str, default: float = 50.0) -> float:
    return float(state_variables.get(state_id, {}).get("value", default) or default)


def derive_current_state(state_variables: Dict[str, Dict[str, Any]], language: str) -> str:
    external = _state_value(state_variables, "external_involvement")
    energy = _state_value(state_variables, "energy_trade_disruption")
    talks = _state_value(state_variables, "negotiation_signals")
    strike = _state_value(state_variables, "strike_capacity")
    logistics = _state_value(state_variables, "logistics_capacity")
    operational = _state_value(state_variables, "operational_control")
    if external >= 65 or energy >= 72:
        return "地区外溢" if language == "zh" else "Regional Spillover"
    if talks >= 62 and strike <= 52 and logistics <= 55 and operational <= 55:
        return "谈判前夜" if language == "zh" else "Pre-Negotiation"
    if strike >= 60 or operational >= 60 or external >= 60:
        return "扩大战" if language == "zh" else "Expansion Phase"
    return "压制战" if language == "zh" else "Containment / Suppression"


def termination_windows(state_variables: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    strike = _state_value(state_variables, "strike_capacity") / 100.0
    logistics = _state_value(state_variables, "logistics_capacity") / 100.0
    c2 = _state_value(state_variables, "command_control") / 100.0
    operational = _state_value(state_variables, "operational_control") / 100.0
    leadership = _state_value(state_variables, "leadership_stability") / 100.0
    domestic = _state_value(state_variables, "domestic_support") / 100.0
    elite = _state_value(state_variables, "elite_cohesion") / 100.0
    economic = _state_value(state_variables, "economic_resilience") / 100.0
    energy = _state_value(state_variables, "energy_trade_disruption") / 100.0
    sanctions = _state_value(state_variables, "sanctions_pressure") / 100.0
    external = _state_value(state_variables, "external_involvement") / 100.0
    talks = _state_value(state_variables, "negotiation_signals") / 100.0

    fast = _clamp(
        0.18 * (1 - strike)
        + 0.14 * (1 - logistics)
        + 0.10 * (1 - c2)
        + 0.08 * (1 - operational)
        + 0.10 * (1 - leadership)
        + 0.08 * (1 - domestic)
        + 0.08 * (1 - elite)
        + 0.06 * (1 - economic)
        + 0.08 * energy
        + 0.08 * sanctions
        + 0.10 * talks
        + 0.10 * (1 - external)
    )
    mid = _clamp(
        0.12 * (1 - strike)
        + 0.12 * (1 - logistics)
        + 0.08 * (1 - c2)
        + 0.08 * (1 - operational)
        + 0.08 * (1 - leadership)
        + 0.08 * (1 - domestic)
        + 0.08 * (1 - elite)
        + 0.06 * (1 - economic)
        + 0.08 * energy
        + 0.10 * sanctions
        + 0.12 * talks
        + 0.08 * (1 - external)
    )
    slow = _clamp(
        0.16 * strike
        + 0.14 * logistics
        + 0.10 * c2
        + 0.08 * operational
        + 0.10 * leadership
        + 0.08 * domestic
        + 0.08 * elite
        + 0.06 * economic
        + 0.06 * (1 - energy)
        + 0.04 * (1 - sanctions)
        + 0.10 * external
        + 0.10 * (1 - talks)
    )

    return [
        {"window_days": 7, "probability": round(0.08 + 0.26 * fast, 4)},
        {"window_days": 14, "probability": round(0.15 + 0.32 * mid, 4)},
        {"window_days": 30, "probability": round(0.24 + 0.42 * (0.55 * mid + 0.45 * fast), 4)},
        {"window_days": 60, "probability": round(0.42 + 0.36 * (1 - slow), 4)},
    ]


def derive_outcome(state_variables: Dict[str, Dict[str, Any]], language: str) -> Dict[str, Any]:
    talks = _state_value(state_variables, "negotiation_signals")
    external = _state_value(state_variables, "external_involvement")
    leadership = _state_value(state_variables, "leadership_stability")
    elite = _state_value(state_variables, "elite_cohesion")
    domestic = _state_value(state_variables, "domestic_support")
    strike = _state_value(state_variables, "strike_capacity")
    sanctions = _state_value(state_variables, "sanctions_pressure")
    energy = _state_value(state_variables, "energy_trade_disruption")
    logistics = _state_value(state_variables, "logistics_capacity")
    operational = _state_value(state_variables, "operational_control")

    candidates = []
    candidates.append(
        (
            "停火" if language == "zh" else "Ceasefire",
            0.35 * (talks / 100.0)
            + 0.20 * (sanctions / 100.0)
            + 0.15 * (energy / 100.0)
            + 0.15 * (1 - strike / 100.0)
            + 0.15 * (1 - external / 100.0),
        )
    )
    candidates.append(
        (
            "冻结冲突" if language == "zh" else "Frozen Conflict",
            0.25 * (leadership / 100.0)
            + 0.20 * (elite / 100.0)
            + 0.20 * (logistics / 100.0)
            + 0.20 * (domestic / 100.0)
            + 0.15 * (1 - talks / 100.0),
        )
    )
    candidates.append(
        (
            "政权裂变" if language == "zh" else "Regime Fracture",
            0.30 * (1 - leadership / 100.0)
            + 0.25 * (1 - elite / 100.0)
            + 0.15 * (1 - domestic / 100.0)
            + 0.15 * (sanctions / 100.0)
            + 0.15 * (talks / 100.0),
        )
    )
    candidates.append(
        (
            "地区扩大战" if language == "zh" else "Regional Expansion",
            0.30 * (external / 100.0)
            + 0.20 * (strike / 100.0)
            + 0.15 * (operational / 100.0)
            + 0.15 * (energy / 100.0)
            + 0.10 * (leadership / 100.0)
            + 0.10 * (1 - talks / 100.0),
        )
    )
    outcome, score = max(candidates, key=lambda pair: pair[1])
    return {"label": outcome, "score": round(score, 4)}


def build_uncertainties(events: List[Dict[str, Any]], state_variables: Dict[str, Dict[str, Any]], language: str) -> List[str]:
    uncertainties = []
    if _state_value(state_variables, "negotiation_signals") >= 58 and _state_value(state_variables, "strike_capacity") >= 55:
        uncertainties.append(
            "谈判信号上升，但打击能力尚未明显下滑，说明相关方可能一边释放斡旋口风，一边保留继续升级的能力。"
            if language == "zh"
            else "Negotiation signals are rising while strike capacity remains intact, suggesting actors may be probing for talks without giving up escalation leverage."
        )
    if _state_value(state_variables, "leadership_stability") <= 45 and _state_value(state_variables, "elite_cohesion") >= 55:
        uncertainties.append(
            "领导层稳定性走弱，但精英联盟尚未明显分裂，这意味着政权可能出现权威受损而非立刻坍塌的过渡状态。"
            if language == "zh"
            else "Leadership stability is weakening while elite cohesion still holds, implying a damaged but not yet collapsing regime core."
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


def build_market_signals(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    oil = []
    prediction_markets = []
    for item in items:
        source = str(item.get("source", ""))
        payload = item.get("payload") or {}
        if source == "oil_market":
            oil.append(
                {
                    "title": item.get("title", ""),
                    "published_at": item.get("published_at"),
                    "url": item.get("url"),
                    "snapshot": item.get("content_text", ""),
                }
            )
        elif source == "polymarket_geopolitics":
            prediction_markets.append(
                {
                    "title": item.get("title", ""),
                    "published_at": item.get("published_at"),
                    "url": item.get("url"),
                    "outcome_prices": payload.get("outcomePrices"),
                    "outcomes": payload.get("outcomes"),
                    "volume": payload.get("volume"),
                    "volume_24h": payload.get("volume24hr"),
                    "liquidity": payload.get("liquidity"),
                }
            )
    return {
        "oil": oil[:4],
        "prediction_markets": prediction_markets[:4],
    }


def build_analysis_package(
    items: List[Dict[str, Any]],
    language: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    events = build_signal_events(items)
    candidate_events = select_diverse_events(events, limit=100, per_source_cap=10)
    judged_events = assess_event_relevance(candidate_events, language=language, model=model)
    related_events = [event for event in judged_events if event.get("decision_related")]
    ranked_related_events = sorted(
        related_events,
        key=lambda event: (
            event.get("relevance_score", 0.0),
            event.get("combined", 0.0),
            event.get("importance", 0.0),
            _parse_timestamp(event.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    analysis_events = select_diverse_events(ranked_related_events, limit=20, per_source_cap=3)
    display_events = sorted(
        select_diverse_events(ranked_related_events, limit=50, per_source_cap=6),
        key=_event_sort_key,
        reverse=True,
    )
    state_list = compute_state_variables(analysis_events, language)
    indicator_groups = group_state_variables(state_list, language)
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
        "framework_version": 2,
        "item_count": len(items),
        "source_mix": source_mix,
        "tension_index": round(
            _clamp(
                (
                    _state_value(state_map, "strike_capacity")
                    + _state_value(state_map, "operational_control")
                    + _state_value(state_map, "external_involvement")
                    + _state_value(state_map, "energy_trade_disruption")
                )
                / 400.0
            )
            * 100.0,
            1,
        ),
        "state_variables": state_list,
        "indicator_groups": indicator_groups,
        "top_events": display_events,
        "all_scored_events": select_diverse_events(events, limit=50, per_source_cap=4),
        "market_signals": build_market_signals(items),
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


def upgrade_summary_framework(summary: Dict[str, Any], language: str) -> Dict[str, Any]:
    if not summary or int(summary.get("framework_version", 0) or 0) >= 2:
        return summary
    items = [dict(item) for item in summary.get("all_scored_events") or summary.get("top_events") or []]
    if not items:
        return summary
    events = build_signal_events(items)
    ranked = sorted(
        events,
        key=lambda event: (
            event.get("decision_related", True),
            event.get("relevance_score", 0.0),
            event.get("combined", 0.0),
            event.get("importance", 0.0),
            _parse_timestamp(event.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    analysis_events = select_diverse_events(ranked, limit=20, per_source_cap=3)
    state_list = compute_state_variables(analysis_events, language)
    indicator_groups = group_state_variables(state_list, language)
    state_map = {state["id"]: state for state in state_list}
    uncertainties = build_uncertainties(analysis_events, state_map, language)
    upgraded = {
        **summary,
        "framework_version": 2,
        "tension_index": round(
            _clamp(
                (
                    _state_value(state_map, "strike_capacity")
                    + _state_value(state_map, "operational_control")
                    + _state_value(state_map, "external_involvement")
                    + _state_value(state_map, "energy_trade_disruption")
                )
                / 400.0
            )
            * 100.0,
            1,
        ),
        "state_variables": state_list,
        "indicator_groups": indicator_groups,
        "decision_panel": {
            **summary.get("decision_panel", {}),
            "current_state": derive_current_state(state_map, language),
            "end_windows": termination_windows(state_map),
            "most_likely_outcome": derive_outcome(state_map, language)["label"],
            "top_decisive_signals": [
                {
                    "title": event["title"],
                    "source": event["source"],
                    "credibility": event["credibility"],
                    "importance": event["importance"],
                }
                for event in analysis_events[:5]
            ],
            "max_uncertainty": uncertainties[:2],
        },
    }
    return upgraded


def localize_summary(summary: Dict[str, Any], language: str, model: Optional[str] = None) -> Dict[str, Any]:
    if not summary:
        return summary
    summary = upgrade_summary_framework(summary, language)
    localized = {
        **summary,
        "top_events": [dict(item) for item in summary.get("top_events", [])],
        "all_scored_events": [dict(item) for item in summary.get("all_scored_events", [])],
        "state_variables": [dict(item) for item in summary.get("state_variables", [])],
        "indicator_groups": [dict(item) for item in summary.get("indicator_groups", [])],
        "decision_panel": {
            **summary.get("decision_panel", {}),
            "top_decisive_signals": [dict(item) for item in summary.get("decision_panel", {}).get("top_decisive_signals", [])],
        },
    }
    variable_lookup = {item["id"]: item for item in VARIABLES}
    label_key = "label_zh" if language == "zh" else "label_en"
    group_key = "group_zh" if language == "zh" else "group_en"
    for item in localized.get("state_variables", []):
        meta = variable_lookup.get(str(item.get("id")))
        if not meta:
            continue
        item["label"] = meta[label_key]
        item["group"] = meta[group_key]
    if not localized.get("indicator_groups") and localized.get("state_variables"):
        localized["indicator_groups"] = group_state_variables(localized["state_variables"], language)
    else:
        normalized_groups = []
        for bucket in localized.get("indicator_groups", []):
            items = [dict(item) for item in bucket.get("items", [])]
            for item in items:
                meta = variable_lookup.get(str(item.get("id")))
                if not meta:
                    continue
                item["label"] = meta[label_key]
                item["group"] = meta[group_key]
            normalized_groups.append(
                {
                    **bucket,
                    "group": items[0].get("group") if items else bucket.get("group"),
                    "items": items,
                }
            )
        localized["indicator_groups"] = normalized_groups
    titles = [str(item.get("title", "")) for item in localized.get("top_events", [])]
    if not titles:
        localized["summary_language"] = language
        return localized

    translated = translate_news_titles(titles, language=language, model=model)
    for item, translated_title in zip(localized["top_events"], translated):
        item.setdefault("title_original", item.get("title", ""))
        item["title"] = translated_title

    reasons = [str(item.get("relevance_reason", "")) for item in localized.get("top_events", [])]
    if any(reason.strip() and not _looks_localized(reason, language) for reason in reasons):
        translated_reasons = translate_brief_texts(reasons, language=language, model=model)
        for item, translated_reason in zip(localized["top_events"], translated_reasons):
            if translated_reason:
                item["relevance_reason"] = translated_reason

    summaries = [str(item.get("brief_summary", "")) for item in localized.get("top_events", [])]
    if any(summary.strip() and not _looks_localized(summary, language) for summary in summaries):
        translated_summaries = translate_brief_texts(summaries, language=language, model=model)
        for item, translated_summary in zip(localized["top_events"], translated_summaries):
            if translated_summary:
                item["brief_summary"] = translated_summary
    for item in localized.get("top_events", []):
        item["brief_summary"] = stabilize_event_summary(item, language=language)

    decisive = localized.get("decision_panel", {}).get("top_decisive_signals", [])
    for item, translated_title in zip(decisive, translated):
        item.setdefault("title_original", item.get("title", ""))
        item["title"] = translated_title

    localized["summary_language"] = language
    localized["top_events"] = sorted(localized.get("top_events", []), key=_event_sort_key, reverse=True)
    return localized
