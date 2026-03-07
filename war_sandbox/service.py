import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import (
    ACLED_API_KEY,
    ACLED_EMAIL,
    DEFAULT_ADSB_INTERVAL_SECONDS,
    DEFAULT_DASHBOARD_REFRESH_SECONDS,
    DEFAULT_FORECAST_INTERVAL_SECONDS,
    DEFAULT_FORECAST_LIMIT,
    DEFAULT_GDELT_INTERVAL_SECONDS,
    DEFAULT_HOURS,
    DEFAULT_LIVEUAMAP_INTERVAL_SECONDS,
    DEFAULT_OFFICIAL_INTERVAL_SECONDS,
    DEFAULT_OPTIONAL_INTERVAL_SECONDS,
    DEFAULT_PORT,
    DEFAULT_QUERY,
    DEFAULT_RELIEFWEB_INTERVAL_SECONDS,
    DEFAULT_RSS_INTERVAL_SECONDS,
    IRAN_BOUNDS,
    MIDDLE_EAST_BOUNDS,
    NASA_FIRMS_MAP_KEY,
    RELIEFWEB_APPNAME,
    REPORT_DIR,
    RSS_CONFIG_PATH,
)
from .db import (
    delete_raw_items_for_source,
    fetch_latest_items_by_sources,
    fetch_recent_items,
    get_forecast,
    get_runtime_setting,
    get_source_config,
    init_db,
    insert_forecast,
    insert_raw_items,
    list_forecasts,
    list_runtime_settings,
    list_source_configs,
    prune_source_configs,
    set_runtime_setting,
    update_source_config,
    update_source_runtime,
    upsert_source_configs,
)
from .report import render_markdown
from .scenario import generate_forecast
from .sources import (
    fetch_acled,
    fetch_adsb_military,
    fetch_centcom_dvids,
    fetch_firms_hotspots,
    fetch_gdelt,
    fetch_gdelt_timeline,
    fetch_idf_releases,
    fetch_iaea_news,
    fetch_irna_english,
    fetch_liveuamap_iran,
    fetch_oil_market,
    fetch_polymarket_geopolitics,
    fetch_presstv_latest,
    fetch_reliefweb,
    fetch_rss,
    fetch_tasnim_english,
    fetch_vesselfinder,
    filter_by_hours,
    load_rss_config,
)
from .war_state import build_analysis_package, localize_summary
from .agent_browser import agent_browser_available


CRITICAL_SNAPSHOT_SOURCES = ("oil_market", "polymarket_geopolitics", "gdelt_timeline")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "source"


def _merge_unique_items(primary: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = {str(item.get("id")): item for item in primary if item.get("id")}
    ordered = [item for item in primary if item.get("id")]
    for item in extra:
        item_id = str(item.get("id"))
        if not item_id or item_id in merged:
            continue
        merged[item_id] = item
        ordered.append(item)
    return ordered


def _row_to_source(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "enabled": bool(row["enabled"]),
        "interval_seconds": row["interval_seconds"],
        "params": json.loads(row["params_json"]),
        "last_run_at": row["last_run_at"],
        "last_status": row["last_status"],
        "last_message": row["last_message"],
        "last_item_count": row["last_item_count"],
    }


def _reliefweb_available(source: Dict[str, Any]) -> bool:
    if source["kind"] != "reliefweb":
        return True
    return bool(source["params"].get("appname"))


def _source_block_reason(source: Dict[str, Any]) -> Optional[str]:
    kind = source["kind"]
    params = source["params"]
    if kind == "idf" and not agent_browser_available():
        return "IDF media releases require Vercel agent-browser"
    if kind == "irna":
        return "IRNA English currently returns a gateway/challenge page from this runtime"
    if kind == "tasnim":
        return "Tasnim English DNS is not resolvable from this runtime"
    if kind == "reliefweb" and not params.get("appname"):
        return "ReliefWeb requires an approved RELIEFWEB_APPNAME"
    if kind == "firms" and not params.get("map_key"):
        return "NASA FIRMS requires a free NASA_FIRMS_MAP_KEY"
    if kind == "acled" and not (params.get("api_key") and params.get("email")):
        return "ACLED requires account credentials and is calibration-only"
    if kind == "vesselfinder":
        return "VesselFinder realtime API is commercial, not a free public feed"
    return None


def _source_group(source: Dict[str, Any]) -> str:
    kind = source.get("kind")
    if kind in {"gdelt", "gdelt_timeline"}:
        return "wire"
    if kind in {"liveuamap", "acled"}:
        return "geo"
    if kind in {"centcom", "idf"}:
        return "official_west"
    if kind in {"irna", "tasnim", "presstv"}:
        return "official_iran"
    if kind == "iaea":
        return "official_international"
    if kind in {"adsb", "firms", "vesselfinder"}:
        return "sensor"
    if kind in {"oil_market", "polymarket"}:
        return "market"
    if kind == "rss":
        return "aggregator"
    return "other"


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = str(value).strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


GRAPH_TEXT = {
    "zh": {
        "tier_high": "高",
        "tier_medium": "中",
        "tier_low": "低",
        "source_intake_title": "源采集",
        "evidence_base_title": "证据基座",
        "signal_extraction_title": "信号提取",
        "causal_assessment_title": "因果驱动评估",
        "scenario_engine_title": "场景引擎",
        "termination_title": "战争结束预测",
        "succession_title": "继任与政策预测",
        "confidence_title": "置信度校准",
        "formula": "C = 100 x clamp(0.30H + 0.20E + 0.15D + 0.10R + 0.10S + 0.15K - 0.18P)",
        "formula_terms": [
            "H = 健康源占比，经关键源覆盖修正",
            "E = min(唯一高价值信号数 / 18, 1)",
            "D = min(来源数 / 5, 1)",
            "R = 24小时内证据占比",
            "S = min((最高结果概率 - 次高结果概率) / 0.35, 1)",
            "K = 关键源组覆盖率，故障组会额外扣分",
        ],
        "source_summary": "{healthy}/{enabled} 个启用源当前健康",
        "evidence_summary": "{items} 条证据，覆盖 {source_count} 类来源",
        "signal_summary": "紧张指数 {tension}，主导参与方 {actors}",
        "causal_summary": "升级 {escalation} / 降级 {deescalation} / 继任 {succession}",
        "scenario_summary": "首要结果场景：{top_outcome}",
        "termination_summary": "P50 结束时间：{p50}",
        "succession_summary": "首位继任场景：{top_successor}",
        "confidence_summary": "综合置信度 {score} / 100（{tier}）",
        "source_assessment": "系统先看哪些源可用、哪些源失效，再决定当前证据面是否足够支撑后续推理。",
        "evidence_assessment": "原始条目先被标准化和裁剪到当前时间窗，再进入后续因果评估。",
        "signal_assessment": "模型前先做确定性信号抽取，避免直接让语言模型在原始新闻流上编故事。",
        "causal_assessment": "这里不是复述新闻，而是把战争升级、降级、继任和人道压力作为驱动变量进入推演。",
        "scenario_assessment": "场景引擎基于上述驱动变量和证据摘要，生成结果概率与政策推演。",
        "termination_assessment": "战争结束时间由场景引擎给出 P10/P50/P90 时间窗，而不是单点预测。",
        "succession_assessment": "继任场景来自条件触发，不把候选人当既成事实。",
        "confidence_assessment": "置信度不是模型一句话，而是对源健康度、样本量、来源多样性、证据新鲜度和场景分离度的显式加权。",
        "metric_enabled": "启用源数",
        "metric_healthy": "健康源数",
        "metric_items": "证据条目",
        "metric_source_types": "来源类型",
        "metric_tension": "紧张指数",
        "metric_top_actor": "最高频参与方",
        "metric_escalation": "升级信号",
        "metric_deescalation": "降级信号",
        "metric_succession": "继任信号",
        "metric_top_outcome": "最高结果概率",
        "metric_p10p50p90": "时间窗",
        "metric_top_successor": "首位继任场景",
        "metric_confidence": "综合置信度",
        "metric_recent": "24小时证据占比",
        "metric_separation": "头两位结果分离度",
    },
    "en": {
        "tier_high": "High",
        "tier_medium": "Medium",
        "tier_low": "Low",
        "source_intake_title": "Source Intake",
        "evidence_base_title": "Evidence Base",
        "signal_extraction_title": "Signal Extraction",
        "causal_assessment_title": "Causal Drivers",
        "scenario_engine_title": "Scenario Engine",
        "termination_title": "War-End Projection",
        "succession_title": "Succession & Policy",
        "confidence_title": "Confidence Calibration",
        "formula": "C = 100 x clamp(0.30H + 0.20E + 0.15D + 0.10R + 0.10S + 0.15K - 0.18P)",
        "formula_terms": [
            "H = healthy-source ratio adjusted by critical-source coverage",
            "E = min(unique high-value signals / 18, 1)",
            "D = min(source count / 5, 1)",
            "R = share of evidence published in the last 24h",
            "S = min((top outcome probability - second outcome probability) / 0.35, 1)",
            "K = critical source-group coverage, with outage penalty",
        ],
        "source_summary": "{healthy}/{enabled} enabled sources are currently healthy",
        "evidence_summary": "{items} items across {source_count} source types",
        "signal_summary": "Tension {tension}; dominant actors {actors}",
        "causal_summary": "Escalation {escalation} / de-escalation {deescalation} / succession {succession}",
        "scenario_summary": "Top outcome scenario: {top_outcome}",
        "termination_summary": "P50 end date: {p50}",
        "succession_summary": "Top successor scenario: {top_successor}",
        "confidence_summary": "Composite confidence {score} / 100 ({tier})",
        "source_assessment": "The system first measures which feeds are usable and which are failing before it trusts the evidence base.",
        "evidence_assessment": "Raw items are normalized and clipped to the active time window before any inference step.",
        "signal_assessment": "Deterministic feature extraction happens before the model call so the pipeline is not just free-form narrative generation.",
        "causal_assessment": "This stage converts news into war drivers: escalation, de-escalation, succession risk, and humanitarian stress.",
        "scenario_assessment": "The scenario engine turns those drivers into end-state probabilities and policy projections.",
        "termination_assessment": "War termination is expressed as a P10/P50/P90 window, not as a fake single-point prediction.",
        "succession_assessment": "Successor outcomes are trigger-based scenarios, not asserted facts about named leaders.",
        "confidence_assessment": "Confidence is not a model sentence. It is an explicit weighted combination of source health, sample size, diversity, freshness, and scenario separation.",
        "metric_enabled": "Enabled sources",
        "metric_healthy": "Healthy sources",
        "metric_items": "Evidence items",
        "metric_source_types": "Source types",
        "metric_tension": "Tension index",
        "metric_top_actor": "Top actor",
        "metric_escalation": "Escalation signals",
        "metric_deescalation": "De-escalation signals",
        "metric_succession": "Succession signals",
        "metric_top_outcome": "Top outcome",
        "metric_p10p50p90": "Window",
        "metric_top_successor": "Top successor",
        "metric_confidence": "Composite confidence",
        "metric_recent": "24h evidence share",
        "metric_separation": "Top-2 separation",
    },
}


def _confidence_metrics(
    summary: Dict[str, Any],
    forecast: Dict[str, Any],
    sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    enabled_sources = [source for source in sources if source["enabled"]]
    healthy_sources = [source for source in enabled_sources if source.get("last_status") == "ok"]
    source_mix = summary.get("source_mix", {})
    evidence_items = summary.get("all_scored_events") or summary.get("top_events") or summary.get("evidence", [])
    item_count = int(summary.get("item_count", 0))
    unique_signals = {
        (
            str(item.get("source", "")).lower(),
            re.sub(r"[^a-z0-9]+", " ", str(item.get("title", "")).lower()).strip(),
        )
        for item in evidence_items
        if item.get("title")
    }
    now = datetime.now(timezone.utc)
    recent_24h = 0
    for item in evidence_items:
        published = _parse_timestamp(item.get("published_at"))
        if published and published >= now - timedelta(hours=24):
            recent_24h += 1

    enabled_groups = {_source_group(source) for source in enabled_sources}
    healthy_groups = {_source_group(source) for source in healthy_sources}
    critical_groups = {"wire", "geo", "official_west", "official_iran", "sensor", "market"}
    required_groups = critical_groups & enabled_groups
    critical_coverage = _safe_ratio(len(healthy_groups & required_groups), len(required_groups))
    blocked_groups = {
        _source_group(source)
        for source in enabled_sources
        if source.get("last_status") in {"error", "blocked"}
    }
    outage_penalty = _clamp(_safe_ratio(len(blocked_groups & required_groups), len(required_groups)))

    outcome_probs = sorted(
        [float(outcome.get("probability", 0.0)) for outcome in forecast.get("outcome_probabilities", [])],
        reverse=True,
    )
    top_gap = 0.0
    if len(outcome_probs) >= 2:
        top_gap = max(0.0, outcome_probs[0] - outcome_probs[1])
    elif outcome_probs:
        top_gap = max(0.0, outcome_probs[0])

    base_health = _clamp(_safe_ratio(len(healthy_sources), len(enabled_sources)))
    health = _clamp(base_health * (0.55 + 0.45 * critical_coverage))
    evidence = _clamp(len(unique_signals) / 18.0)
    diversity = _clamp(len({value for value in source_mix if value}) / 5.0)
    recency = _clamp(_safe_ratio(recent_24h, item_count))
    separation = _clamp(top_gap / 0.35)
    raw = 0.30 * health + 0.20 * evidence + 0.15 * diversity + 0.10 * recency + 0.10 * separation + 0.15 * critical_coverage
    score = round(_clamp(raw - 0.18 * outage_penalty) * 100.0, 1)

    return {
        "score": score,
        "health": round(health, 4),
        "evidence": round(evidence, 4),
        "diversity": round(diversity, 4),
        "recency": round(recency, 4),
        "separation": round(separation, 4),
        "critical_coverage": round(critical_coverage, 4),
        "outage_penalty": round(outage_penalty, 4),
        "unique_signals": len(unique_signals),
        "enabled_sources": len(enabled_sources),
        "healthy_sources": len(healthy_sources),
        "recent_24h": recent_24h,
        "top_gap": round(top_gap, 4),
    }


def _confidence_tier(score: float, language: str) -> str:
    text = GRAPH_TEXT.get(language, GRAPH_TEXT["zh"])
    if score >= 75:
        return text["tier_high"]
    if score >= 55:
        return text["tier_medium"]
    return text["tier_low"]


def _build_reasoning_graph(
    summary: Dict[str, Any],
    forecast: Dict[str, Any],
    sources: List[Dict[str, Any]],
    language: str,
) -> Dict[str, Any]:
    text = GRAPH_TEXT.get(language, GRAPH_TEXT["zh"])
    state_variables = {item["id"]: item for item in summary.get("state_variables", [])}
    top_events = summary.get("top_events", [])
    top_actor = top_events[0]["source"] if top_events else "-"
    actor_preview = ", ".join(event["source"] for event in top_events[:3]) or "-"
    outcomes = forecast.get("outcome_probabilities", [])
    top_outcome = outcomes[0]["scenario"] if outcomes else "-"
    successor_scenarios = forecast.get("successor_government_scenarios", [])
    top_successor = successor_scenarios[0]["name"] if successor_scenarios else "-"
    source_mix = summary.get("source_mix", {})
    confidence = _confidence_metrics(summary, forecast, sources)
    tier = _confidence_tier(confidence["score"], language)

    nodes = [
        {
            "id": "source_intake",
            "title": text["source_intake_title"],
            "score": round(confidence["health"] * 100, 1),
            "summary": text["source_summary"].format(
                healthy=confidence["healthy_sources"],
                enabled=confidence["enabled_sources"],
            ),
            "assessment": text["source_assessment"],
            "metrics": [
                {"label": text["metric_enabled"], "value": str(confidence["enabled_sources"])},
                {"label": text["metric_healthy"], "value": str(confidence["healthy_sources"])},
            ],
            "details": [
                f"{source['name']}: {source.get('last_status') or 'idle'} / {source.get('last_message') or '-'}"
                for source in sources
            ],
        },
        {
            "id": "evidence_base",
            "title": text["evidence_base_title"],
            "score": round(confidence["evidence"] * 100, 1),
            "summary": text["evidence_summary"].format(
                items=summary.get("item_count", 0),
                source_count=len(source_mix),
            ),
            "assessment": text["evidence_assessment"],
            "metrics": [
                {"label": text["metric_items"], "value": str(summary.get("item_count", 0))},
                {"label": text["metric_source_types"], "value": str(len(source_mix))},
            ],
            "details": [f"{key}: {value}" for key, value in source_mix.items()],
        },
        {
            "id": "signal_extraction",
            "title": text["signal_extraction_title"],
            "score": float(summary.get("tension_index", 0.0)),
            "summary": text["signal_summary"].format(
                tension=summary.get("tension_index", 0.0),
                actors=actor_preview,
            ),
            "assessment": text["signal_assessment"],
            "metrics": [
                {"label": text["metric_tension"], "value": str(summary.get("tension_index", 0.0))},
                {"label": text["metric_top_actor"], "value": top_actor},
            ],
            "details": [event["title"] for event in top_events[:6]],
        },
        {
            "id": "causal_assessment",
            "title": text["causal_assessment_title"],
            "score": round(
                min(
                    100.0,
                    (
                        state_variables.get("missile_drone_capacity", {}).get("value", 0.0)
                        + state_variables.get("new_state_involvement", {}).get("value", 0.0)
                        + state_variables.get("us_objective_expansion", {}).get("value", 0.0)
                    )
                    / 3.0,
                ),
                1,
            ),
            "summary": text["causal_summary"].format(
                escalation=round(state_variables.get("missile_drone_capacity", {}).get("value", 0.0), 1),
                deescalation=round(state_variables.get("domestic_instability_talks", {}).get("value", 0.0), 1),
                succession=round(state_variables.get("command_chain_stability", {}).get("value", 0.0), 1),
            ),
            "assessment": text["causal_assessment"],
            "metrics": [
                {
                    "label": text["metric_escalation"],
                    "value": str(state_variables.get("missile_drone_capacity", {}).get("value", 0.0)),
                },
                {
                    "label": text["metric_deescalation"],
                    "value": str(state_variables.get("domestic_instability_talks", {}).get("value", 0.0)),
                },
                {
                    "label": text["metric_succession"],
                    "value": str(state_variables.get("command_chain_stability", {}).get("value", 0.0)),
                },
            ],
            "details": [f"{item['label']}: {item['value']} ({item['direction']})" for item in summary.get("state_variables", [])],
        },
        {
            "id": "scenario_engine",
            "title": text["scenario_engine_title"],
            "score": round(confidence["separation"] * 100, 1),
            "summary": text["scenario_summary"].format(top_outcome=top_outcome),
            "assessment": text["scenario_assessment"],
            "metrics": [
                {"label": text["metric_top_outcome"], "value": top_outcome},
                {"label": text["metric_separation"], "value": str(confidence["top_gap"])},
            ],
            "details": [
                f"{outcome.get('scenario', '-')}: {outcome.get('probability', 0)}"
                for outcome in outcomes[:4]
            ],
        },
        {
            "id": "termination_projection",
            "title": text["termination_title"],
            "score": round(confidence["recency"] * 100, 1),
            "summary": text["termination_summary"].format(
                p50=forecast.get("war_end_window", {}).get("p50", "-")
            ),
            "assessment": text["termination_assessment"],
            "metrics": [
                {
                    "label": text["metric_p10p50p90"],
                    "value": " / ".join(
                        [
                            str(forecast.get("war_end_window", {}).get("p10", "-")),
                            str(forecast.get("war_end_window", {}).get("p50", "-")),
                            str(forecast.get("war_end_window", {}).get("p90", "-")),
                        ]
                    ),
                }
            ],
            "details": [str(forecast.get("war_end_window", {}).get("rationale", "-"))],
        },
        {
            "id": "succession_projection",
            "title": text["succession_title"],
            "score": round((float(successor_scenarios[0].get("probability", 0.0)) if successor_scenarios else 0.0) * 100, 1),
            "summary": text["succession_summary"].format(top_successor=top_successor),
            "assessment": text["succession_assessment"],
            "metrics": [
                {"label": text["metric_top_successor"], "value": top_successor},
            ],
            "details": [
                f"{scenario.get('name', '-')}: {scenario.get('probability', 0)} / {scenario.get('trigger_conditions', '-')}"
                for scenario in successor_scenarios[:3]
            ],
        },
        {
            "id": "confidence_calibration",
            "title": text["confidence_title"],
            "score": confidence["score"],
            "summary": text["confidence_summary"].format(score=confidence["score"], tier=tier),
            "assessment": text["confidence_assessment"],
            "metrics": [
                {"label": text["metric_confidence"], "value": str(confidence["score"])},
                {"label": "H", "value": str(confidence["health"])},
                {"label": "E", "value": str(confidence["evidence"])},
                {"label": "D", "value": str(confidence["diversity"])},
                {"label": "R", "value": str(confidence["recency"])},
                {"label": "S", "value": str(confidence["separation"])},
                {"label": "K", "value": str(confidence["critical_coverage"])},
                {"label": "P", "value": str(confidence["outage_penalty"])},
            ],
            "details": text["formula_terms"],
            "formula": text["formula"],
        },
    ]

    edges = [
        {"from": "source_intake", "to": "evidence_base"},
        {"from": "evidence_base", "to": "signal_extraction"},
        {"from": "signal_extraction", "to": "causal_assessment"},
        {"from": "causal_assessment", "to": "scenario_engine"},
        {"from": "scenario_engine", "to": "termination_projection"},
        {"from": "scenario_engine", "to": "succession_projection"},
        {"from": "termination_projection", "to": "confidence_calibration"},
        {"from": "succession_projection", "to": "confidence_calibration"},
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "confidence": {
            **confidence,
            "tier": tier,
            "formula": text["formula"],
            "terms": text["formula_terms"],
        },
    }


def default_source_configs(rss_path: str = str(RSS_CONFIG_PATH)) -> List[Dict[str, Any]]:
    configs = [
        {
            "id": "gdelt_articles",
            "name": "GDELT Article List RSS",
            "kind": "gdelt",
            "enabled": True,
            "interval_seconds": DEFAULT_GDELT_INTERVAL_SECONDS,
            "params": {
                "query": DEFAULT_QUERY,
                "hours": DEFAULT_HOURS,
                "max_records": 50,
            },
        },
        {
            "id": "gdelt_timeline",
            "name": "GDELT Event / GKG Pulse",
            "kind": "gdelt_timeline",
            "enabled": True,
            "interval_seconds": DEFAULT_GDELT_INTERVAL_SECONDS,
            "params": {
                "query": DEFAULT_QUERY,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "google_news_iran_conflict",
            "name": "Google News Iran Conflict",
            "kind": "rss",
            "enabled": True,
            "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
            "params": {
                "url": "https://news.google.com/rss/search?q=Iran+Israel+war&hl=en-US&gl=US&ceid=US:en",
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "centcom_dvids",
            "name": "CENTCOM Press Releases",
            "kind": "centcom",
            "enabled": True,
            "interval_seconds": DEFAULT_OFFICIAL_INTERVAL_SECONDS,
            "params": {
                "max_records": 12,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "idf_releases",
            "name": "IDF Media Releases",
            "kind": "idf",
            "enabled": True,
            "interval_seconds": DEFAULT_OFFICIAL_INTERVAL_SECONDS,
            "params": {
                "max_records": 12,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "presstv_latest",
            "name": "PressTV Latest",
            "kind": "presstv",
            "enabled": True,
            "interval_seconds": DEFAULT_OFFICIAL_INTERVAL_SECONDS,
            "params": {
                "max_records": 12,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "google_news_hormuz_shipping",
            "name": "Google News Hormuz Shipping",
            "kind": "rss",
            "enabled": True,
            "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
            "params": {
                "url": "https://news.google.com/rss/search?q=Hormuz+shipping+Iran&hl=en-US&gl=US&ceid=US:en",
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "radiofarda_iran",
            "name": "Radio Farda Iran News",
            "kind": "rss",
            "enabled": True,
            "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
            "params": {
                "url": "https://en.radiofarda.com/api/zp_qmtl-vomx-tpe_bimr",
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "unnews_middle_east",
            "name": "UN News Middle East",
            "kind": "rss",
            "enabled": True,
            "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
            "params": {
                "url": "https://news.un.org/feed/subscribe/en/news/region/middle-east/feed/rss.xml",
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "unnews_peace_security",
            "name": "UN News Peace and Security",
            "kind": "rss",
            "enabled": True,
            "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
            "params": {
                "url": "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml",
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "iaea_news",
            "name": "IAEA News",
            "kind": "iaea",
            "enabled": True,
            "interval_seconds": DEFAULT_OFFICIAL_INTERVAL_SECONDS,
            "params": {
                "max_records": 12,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "adsb_military",
            "name": "ADSB.lol Military Traffic",
            "kind": "adsb",
            "enabled": True,
            "interval_seconds": DEFAULT_ADSB_INTERVAL_SECONDS,
            "params": {
                **MIDDLE_EAST_BOUNDS,
                "limit": 40,
                "hours": 3,
            },
        },
        {
            "id": "oil_market",
            "name": "International Crude Oil",
            "kind": "oil_market",
            "enabled": True,
            "interval_seconds": DEFAULT_ADSB_INTERVAL_SECONDS,
            "params": {
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "polymarket_geopolitics",
            "name": "Polymarket Geopolitical Markets",
            "kind": "polymarket",
            "enabled": True,
            "interval_seconds": DEFAULT_ADSB_INTERVAL_SECONDS,
            "params": {
                "hours": DEFAULT_HOURS,
                "limit": 8,
            },
        },
        {
            "id": "nasa_firms",
            "name": "NASA FIRMS Hotspots",
            "kind": "firms",
            "enabled": bool(NASA_FIRMS_MAP_KEY),
            "interval_seconds": DEFAULT_OPTIONAL_INTERVAL_SECONDS,
            "params": {
                **IRAN_BOUNDS,
                "map_key": NASA_FIRMS_MAP_KEY,
                "day_range": 1,
                "limit": 50,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "acled_calibration",
            "name": "ACLED Calibration",
            "kind": "acled",
            "enabled": bool(ACLED_API_KEY and ACLED_EMAIL),
            "interval_seconds": DEFAULT_OPTIONAL_INTERVAL_SECONDS,
            "params": {
                "api_key": ACLED_API_KEY,
                "email": ACLED_EMAIL,
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "vesselfinder_hormuz",
            "name": "VesselFinder Hormuz",
            "kind": "vesselfinder",
            "enabled": False,
            "interval_seconds": DEFAULT_OPTIONAL_INTERVAL_SECONDS,
            "params": {
                "hours": DEFAULT_HOURS,
            },
        },
        {
            "id": "reliefweb",
            "name": "ReliefWeb Reports",
            "kind": "reliefweb",
            "enabled": bool(RELIEFWEB_APPNAME),
            "interval_seconds": DEFAULT_RELIEFWEB_INTERVAL_SECONDS,
            "params": {
                "query": DEFAULT_QUERY,
                "hours": DEFAULT_HOURS,
                "limit": 20,
                "appname": RELIEFWEB_APPNAME,
            },
        },
    ]
    try:
        for feed in load_rss_config(rss_path):
            configs.append(
                {
                    "id": f"rss_{slugify(feed['name'])}",
                    "name": feed["name"],
                    "kind": "rss",
                    "enabled": True,
                    "interval_seconds": DEFAULT_RSS_INTERVAL_SECONDS,
                    "params": {
                        "url": feed["url"],
                        "hours": DEFAULT_HOURS,
                    },
                }
            )
    except FileNotFoundError:
        pass
    return configs


def bootstrap_state(rss_path: str = str(RSS_CONFIG_PATH)) -> None:
    init_db()
    upsert_source_configs(default_source_configs(rss_path=rss_path))
    defaults = {
        "forecast_interval_seconds": DEFAULT_FORECAST_INTERVAL_SECONDS,
        "auto_forecast": True,
        "dashboard_refresh_seconds": DEFAULT_DASHBOARD_REFRESH_SECONDS,
        "evidence_hours": DEFAULT_HOURS,
        "forecast_limit": DEFAULT_FORECAST_LIMIT,
        "default_port": DEFAULT_PORT,
        "language": "zh",
    }
    for key, value in defaults.items():
        if get_runtime_setting(key) is None:
            set_runtime_setting(key, value)
    if get_runtime_setting("evidence_hours") != DEFAULT_HOURS:
        set_runtime_setting("evidence_hours", DEFAULT_HOURS)
    current_limit = int(get_runtime_setting("forecast_limit", DEFAULT_FORECAST_LIMIT) or DEFAULT_FORECAST_LIMIT)
    if current_limit < DEFAULT_FORECAST_LIMIT:
        set_runtime_setting("forecast_limit", DEFAULT_FORECAST_LIMIT)


class SandboxService:
    def __init__(self, rss_path: str = str(RSS_CONFIG_PATH), model: Optional[str] = None):
        self.rss_path = rss_path
        self.model = model
        self.lock = threading.Lock()

    def sync_sources(self) -> None:
        configs = default_source_configs(rss_path=self.rss_path)
        upsert_source_configs(configs)
        prune_source_configs(row["id"] for row in configs)
        for row in list_source_configs():
            source = _row_to_source(row)
            block_reason = _source_block_reason(source)
            if block_reason:
                update_source_config(source["id"], False, source["interval_seconds"])
                update_source_runtime(
                    source["id"],
                    last_run_at=utc_now_iso(),
                    last_status="blocked",
                    last_message=block_reason,
                    last_item_count=0,
                )
                continue
            # Re-enable previously blocked IDF source now that browser-backed collection exists.
            if source["kind"] == "idf" and not source["enabled"]:
                update_source_config(source["id"], True, source["interval_seconds"])

    def list_sources(self) -> List[Dict[str, Any]]:
        self.sync_sources()
        return [_row_to_source(row) for row in list_source_configs()]

    def list_settings(self) -> Dict[str, Any]:
        return list_runtime_settings()

    def update_source(self, source_id: str, enabled: bool, interval_seconds: int) -> None:
        row = get_source_config(source_id)
        if not row:
            raise ValueError(f"Unknown source: {source_id}")
        source = _row_to_source(row)
        block_reason = _source_block_reason(source)
        if enabled and block_reason:
            update_source_config(source_id, False, max(60, int(interval_seconds)))
            update_source_runtime(
                source_id,
                last_run_at=utc_now_iso(),
                last_status="blocked",
                last_message=block_reason,
                last_item_count=0,
            )
            return
        update_source_config(source_id, enabled, max(60, int(interval_seconds)))

    def update_settings(self, settings: Dict[str, Any]) -> None:
        for key, value in settings.items():
            if key == "evidence_hours":
                value = DEFAULT_HOURS
            if key == "forecast_limit":
                value = max(DEFAULT_FORECAST_LIMIT, int(value))
            set_runtime_setting(key, value)

    def run_source(self, source_id: str) -> Dict[str, Any]:
        with self.lock:
            row = get_source_config(source_id)
            if not row:
                raise ValueError(f"Unknown source: {source_id}")
            source = _row_to_source(row)
            params = source["params"]
            hours = int(params.get("hours", DEFAULT_HOURS))
            items = []
            block_reason = _source_block_reason(source)
            if block_reason:
                raise ValueError(block_reason)
            if source["kind"] == "gdelt":
                items = fetch_gdelt(
                    params.get("query", DEFAULT_QUERY),
                    max_records=int(params.get("max_records", 50)),
                    hours=hours,
                )
            elif source["kind"] == "gdelt_timeline":
                items = fetch_gdelt_timeline(
                    params.get("query", DEFAULT_QUERY),
                    hours=hours,
                )
            elif source["kind"] == "liveuamap":
                items = fetch_liveuamap_iran(max_records=int(params.get("max_records", 20)))
            elif source["kind"] == "centcom":
                items = fetch_centcom_dvids(max_records=int(params.get("max_records", 12)))
            elif source["kind"] == "iaea":
                items = fetch_iaea_news(max_records=int(params.get("max_records", 12)))
            elif source["kind"] == "idf":
                items = fetch_idf_releases(max_records=int(params.get("max_records", 12)))
            elif source["kind"] == "irna":
                items = fetch_irna_english()
            elif source["kind"] == "tasnim":
                items = fetch_tasnim_english()
            elif source["kind"] == "presstv":
                items = fetch_presstv_latest(max_records=int(params.get("max_records", 12)))
            elif source["kind"] == "adsb":
                items = fetch_adsb_military(
                    {
                        "lat_min": float(params.get("lat_min", MIDDLE_EAST_BOUNDS["lat_min"])),
                        "lat_max": float(params.get("lat_max", MIDDLE_EAST_BOUNDS["lat_max"])),
                        "lon_min": float(params.get("lon_min", MIDDLE_EAST_BOUNDS["lon_min"])),
                        "lon_max": float(params.get("lon_max", MIDDLE_EAST_BOUNDS["lon_max"])),
                    },
                    limit=int(params.get("limit", 40)),
                )
            elif source["kind"] == "oil_market":
                items = fetch_oil_market()
            elif source["kind"] == "polymarket":
                items = fetch_polymarket_geopolitics(limit=int(params.get("limit", 8)))
            elif source["kind"] == "firms":
                items = fetch_firms_hotspots(
                    map_key=params["map_key"],
                    west=float(params.get("west", IRAN_BOUNDS["west"])),
                    south=float(params.get("south", IRAN_BOUNDS["south"])),
                    east=float(params.get("east", IRAN_BOUNDS["east"])),
                    north=float(params.get("north", IRAN_BOUNDS["north"])),
                    day_range=int(params.get("day_range", 1)),
                    limit=int(params.get("limit", 50)),
                )
            elif source["kind"] == "acled":
                items = fetch_acled()
            elif source["kind"] == "vesselfinder":
                items = fetch_vesselfinder()
            elif source["kind"] == "reliefweb":
                appname = params.get("appname")
                if not appname:
                    raise ValueError("ReliefWeb requires an approved RELIEFWEB_APPNAME")
                items = fetch_reliefweb(
                    params.get("query", DEFAULT_QUERY),
                    limit=int(params.get("limit", 20)),
                    appname=appname,
                )
            elif source["kind"] == "rss":
                items = fetch_rss(source["name"], params["url"])
            else:
                raise ValueError(f"Unsupported source kind: {source['kind']}")

            filtered = filter_by_hours(items, hours)
            if source["kind"] in {"oil_market", "polymarket"}:
                delete_raw_items_for_source(source["id"])
            inserted = insert_raw_items(filtered)
            now = utc_now_iso()
            update_source_runtime(
                source_id,
                last_run_at=now,
                last_status="ok",
                last_message=f"inserted {inserted} items",
                last_item_count=inserted,
            )
            return {
                "source_id": source_id,
                "inserted": inserted,
                "fetched": len(items),
                "status": "ok",
            }

    def run_source_safe(self, source_id: str) -> Dict[str, Any]:
        try:
            return self.run_source(source_id)
        except Exception as exc:  # noqa: BLE001
            now = utc_now_iso()
            update_source_runtime(
                source_id,
                last_run_at=now,
                last_status="error",
                last_message=str(exc),
                last_item_count=0,
            )
            return {
                "source_id": source_id,
                "inserted": 0,
                "status": "error",
                "message": str(exc),
            }

    def run_forecast(self) -> Dict[str, Any]:
        with self.lock:
            settings = self.list_settings()
            hours = DEFAULT_HOURS
            limit = max(int(settings.get("forecast_limit", DEFAULT_FORECAST_LIMIT)), DEFAULT_FORECAST_LIMIT)
            language = settings.get("language", "zh")
            items = fetch_recent_items(hours, limit=limit)
            items = _merge_unique_items(items, fetch_latest_items_by_sources(CRITICAL_SNAPSHOT_SOURCES))
            if not items:
                raise ValueError("No evidence items found for forecasting")
            summary = build_analysis_package(items, language=language, model=self.model)
            forecast = generate_forecast(summary, model=self.model, language=language)
            created_at = utc_now_iso()
            report_markdown = render_markdown(summary, forecast, language=language)
            forecast_id = forecast["forecast_id"]
            insert_forecast(
                forecast_id=forecast_id,
                created_at=created_at,
                evidence_hours=hours,
                model=self.model or "default",
                summary=summary,
                forecast=forecast,
                report_markdown=report_markdown,
            )
            report_path = REPORT_DIR / f"{forecast_id}.md"
            report_path.write_text(report_markdown, encoding="utf-8")
            set_runtime_setting("last_forecast_at", created_at)
            return {
                "forecast_id": forecast_id,
                "report_path": str(report_path),
                "items_used": len(items),
            }

    def latest_forecast_state(self) -> Dict[str, Any]:
        row = get_forecast()
        if not row:
            return {}
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "evidence_hours": row["evidence_hours"],
            "model": row["model"],
            "forecast": json.loads(row["forecast_json"]),
            "summary": json.loads(row["summary_json"]),
            "report_markdown": row["report_markdown"],
        }

    def recent_forecasts(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = list_forecasts(limit=limit)
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "evidence_hours": row["evidence_hours"],
                "model": row["model"],
            }
            for row in rows
        ]

    def dashboard_state(self) -> Dict[str, Any]:
        settings = self.list_settings()
        language = settings.get("language", "zh")
        latest = self.latest_forecast_state()
        if latest:
            latest["summary"] = localize_summary(
                latest.get("summary", {}),
                language=language,
                model=self.model,
            )
        sources = self.list_sources()
        reasoning_graph = {}
        if latest:
            reasoning_graph = _build_reasoning_graph(
                latest.get("summary", {}),
                latest.get("forecast", {}),
                sources,
                language,
            )
        return {
            "settings": settings,
            "sources": sources,
            "latest_forecast": latest,
            "recent_forecasts": self.recent_forecasts(),
            "reasoning_graph": reasoning_graph,
        }

    def source_due(self, source: Dict[str, Any]) -> bool:
        if not source["enabled"]:
            return False
        last_run_at = source.get("last_run_at")
        if not last_run_at:
            return True
        last = datetime.fromisoformat(last_run_at)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= int(source["interval_seconds"])

    def forecast_due(self) -> bool:
        settings = self.list_settings()
        if not settings.get("auto_forecast", True):
            return False
        interval_seconds = int(
            settings.get("forecast_interval_seconds", DEFAULT_FORECAST_INTERVAL_SECONDS)
        )
        last_forecast_at = settings.get("last_forecast_at")
        if not last_forecast_at:
            return True
        last = datetime.fromisoformat(last_forecast_at)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= interval_seconds

    def tick(self) -> Dict[str, Any]:
        results = {"sources": [], "forecast": None}
        for source in self.list_sources():
            if self.source_due(source):
                results["sources"].append(self.run_source_safe(source["id"]))
        if self.forecast_due():
            try:
                results["forecast"] = self.run_forecast()
            except Exception as exc:  # noqa: BLE001
                results["forecast"] = {"status": "error", "message": str(exc)}
        return results

    def loop_forever(self, stop_event: threading.Event, sleep_seconds: int = 5) -> None:
        while not stop_event.is_set():
            self.tick()
            stop_event.wait(sleep_seconds)
