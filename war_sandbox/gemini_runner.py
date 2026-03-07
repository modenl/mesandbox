import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from html import unescape
from typing import Any, Dict, List, Optional


class GeminiError(RuntimeError):
    pass


def _gemini_executable() -> str:
    candidates = [
        os.environ.get("GEMINI_BIN"),
        shutil.which("gemini"),
        "/opt/homebrew/bin/gemini",
        "/usr/local/bin/gemini",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise GeminiError("Could not locate gemini executable")


def extract_json_value(text: str) -> Any:
    text = text.strip()
    if not text:
        raise GeminiError("Empty Gemini response")

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    decoder = json.JSONDecoder()
    for start in range(len(text)):
        if text[start] not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
            return value
        except json.JSONDecodeError:
            continue
    raise GeminiError("Could not find JSON value in Gemini response")


def extract_json_blob(text: str) -> Dict[str, Any]:
    value = extract_json_value(text)
    if not isinstance(value, dict):
        raise GeminiError("Expected JSON object in Gemini response")
    return value


def run_text_prompt(prompt: str, model: Optional[str] = None) -> str:
    cmd = [_gemini_executable(), "-p", prompt, "-o", "json"]
    if model:
        cmd.extend(["-m", model])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GeminiError(result.stderr.strip() or result.stdout.strip())

    outer = json.loads(result.stdout)
    return str(outer.get("response", "")).strip()


def run_structured_prompt(prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
    response = run_text_prompt(prompt, model=model)
    return extract_json_blob(response)


def _strip_markup(text: str) -> str:
    value = unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ").replace("&nbsp;", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_kv_blob(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for chunk in (text or "").split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            result[key] = value
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalized_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").lower())


def _format_number(value: float, language: str) -> str:
    number = _safe_float(value)
    if not number:
        return "0"
    abs_number = abs(number)
    if language == "zh":
        if abs_number >= 100000000:
            return f"{number / 100000000:.2f}亿"
        if abs_number >= 10000:
            return f"{number / 10000:.2f}万"
        return f"{number:.0f}" if abs_number >= 100 else f"{number:.2f}"
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs_number >= 1_000:
        return f"{number / 1_000:.2f}K"
    return f"{number:.0f}" if abs_number >= 100 else f"{number:.2f}"


def _looks_redundant(title: str, summary: str) -> bool:
    clean_summary = _strip_markup(summary)
    if len(clean_summary) < 28:
        return True
    title_norm = _normalized_text(title)
    summary_norm = _normalized_text(clean_summary)
    if not title_norm or not summary_norm:
        return not clean_summary
    if summary_norm.startswith(title_norm):
        return True
    if title_norm in summary_norm and len(summary_norm) - len(title_norm) < 32:
        return True
    title_tokens = {token for token in re.findall(r"[a-z0-9]+", (title or "").lower()) if len(token) >= 3}
    if title_tokens:
        overlap = sum(1 for token in title_tokens if token in summary_norm)
        if overlap >= max(2, len(title_tokens) - 1) and len(clean_summary) < len(title) + 40:
            return True
    return False


def _truncate_sentence(text: str, limit: int) -> str:
    clean = _strip_markup(text)
    if len(clean) <= limit:
        return clean
    cutoff = max(clean.rfind("。", 0, limit), clean.rfind(".", 0, limit), clean.rfind(";", 0, limit))
    if cutoff >= 24:
        return clean[: cutoff + 1].strip()
    return clean[: limit - 1].rstrip() + "…"


def _oil_summary(event: Dict[str, Any], language: str) -> str:
    fields = _parse_kv_blob(str(event.get("content_text", "")))
    benchmark = fields.get("benchmark") or event.get("title") or "Crude oil"
    price = _safe_float(fields.get("regular_market_price"))
    previous_close = _safe_float(fields.get("previous_close"))
    abs_change = _safe_float(fields.get("abs_change"))
    pct_change = _safe_float(fields.get("pct_change"))
    day_high = _safe_float(fields.get("day_high"))
    day_low = _safe_float(fields.get("day_low"))
    volume = _format_number(_safe_float(fields.get("volume")), language)
    currency = fields.get("currency") or "USD"
    if language == "zh":
        direction = "上涨" if pct_change >= 0 else "下跌"
        return (
            f"{benchmark}最新报{price:.2f}{currency}，较前收{direction}{abs_change:.2f}（{pct_change:.1f}%）；"
            f"盘中区间{day_low:.2f}-{day_high:.2f}，成交量约{volume}，直接反映霍尔木兹风险对能源定价的冲击。"
        )
    direction = "up" if pct_change >= 0 else "down"
    return (
        f"{benchmark} last traded at {price:.2f} {currency}, {direction} {abs_change:.2f} ({pct_change:.1f}%) versus the prior close; "
        f"intraday range was {day_low:.2f}-{day_high:.2f} with volume around {volume}, showing how shipping risk is feeding into energy pricing."
    )


def _polymarket_summary(event: Dict[str, Any], language: str) -> str:
    fields = _parse_kv_blob(str(event.get("content_text", "")))
    outcome_blob = fields.get("outcome_prices", "")
    outcome_name = ""
    outcome_value = 0.0
    for part in outcome_blob.split(","):
        if "=" not in part:
            continue
        label, value = part.split("=", 1)
        score = _safe_float(value)
        if score >= outcome_value:
            outcome_name = label.strip()
            outcome_value = score
    volume_24h = _format_number(event.get("market_volume_24h") or fields.get("volume24hr"), language)
    volume_total = _format_number(event.get("market_volume") or fields.get("volume"), language)
    liquidity = _format_number(event.get("market_liquidity") or fields.get("liquidity"), language)
    description = _truncate_sentence(fields.get("description", ""), 88 if language == "zh" else 132)
    if language == "zh":
        trigger = f"判定条件是{description}" if description else "说明市场参与者正在根据明确定义的触发条件下注。"
        return (
            f"该市场当前主导结果为“{outcome_name or '主要选项'}”约{outcome_value * 100:.1f}%，"
            f"24小时成交约{volume_24h}、累计成交约{volume_total}、流动性约{liquidity}；{trigger}"
        )
    trigger = f"Resolution trigger: {description}" if description else "Traders are pricing against a clearly defined resolution condition."
    return (
        f"The market is pricing the leading outcome \"{outcome_name or 'primary side'}\" at roughly {outcome_value * 100:.1f}%, "
        f"with about {volume_24h} in 24h volume, {volume_total} total volume, and {liquidity} liquidity. {trigger}"
    )


def _adsb_summary(event: Dict[str, Any], language: str) -> str:
    fields = _parse_kv_blob(str(event.get("content_text", "")))
    lat = fields.get("lat", "-")
    lon = fields.get("lon", "-")
    alt = fields.get("alt", "-")
    gs = fields.get("gs", "-")
    track = fields.get("track", "-")
    reg = fields.get("registration") or fields.get("hex") or "-"
    if language == "zh":
        return (
            f"ADSB 记录显示该航班位于 {lat},{lon} 一带，高度约 {alt} 英尺、地速 {gs} 节、航向 {track}；"
            f"识别码 {reg}，可用于判断增援、预警或空中保障活动是否仍在加密。"
        )
    return (
        f"ADSB placed the flight near {lat},{lon} at about {alt} ft and {gs} kt on heading {track}; "
        f"track identifier {reg}, which helps judge whether reinforcement, AEW, or air-support activity is intensifying."
    )


def _generic_summary(event: Dict[str, Any], language: str) -> str:
    content = _strip_markup(str(event.get("content_text", "")))
    if not content:
        if language == "zh":
            return "该条目缺少足够正文细节，但仍被保留，因为其来源和时间点对判断战局阶段具有直接参考价值。"
        return "This item carries limited body text, but it is retained because its source and timing still bear directly on the conflict assessment."
    if language == "zh":
        return _truncate_sentence(content, 110)
    return _truncate_sentence(content, 170)


def stabilize_event_summary(event: Dict[str, Any], language: str) -> str:
    summary = _strip_markup(str(event.get("brief_summary", "")))
    title = str(event.get("title", ""))
    if summary and not _looks_redundant(title, summary):
        return summary
    source = str(event.get("source", ""))
    if source == "oil_market":
        return _oil_summary(event, language)
    if source == "polymarket_geopolitics":
        return _polymarket_summary(event, language)
    if source == "adsb_military":
        return _adsb_summary(event, language)
    return _generic_summary(event, language)


def _build_event_context(event: Dict[str, Any]) -> str:
    details = []
    content = _strip_markup(str(event.get("content_text", "")))
    if content:
        details.append(f"content={content[:700]}")
    market_volume_24h = _safe_float(event.get("market_volume_24h"))
    market_volume = _safe_float(event.get("market_volume"))
    market_liquidity = _safe_float(event.get("market_liquidity"))
    if market_volume_24h:
        details.append(f"market_volume_24h={market_volume_24h}")
    if market_volume:
        details.append(f"market_volume={market_volume}")
    if market_liquidity:
        details.append(f"market_liquidity={market_liquidity}")
    return "; ".join(details)


@lru_cache(maxsize=256)
def _translate_title_batch_cached(
    language: str,
    titles_json: str,
    model: Optional[str],
) -> tuple[str, ...]:
    titles = json.loads(titles_json)
    if not titles:
        return tuple()
    target_language = "Simplified Chinese" if language == "zh" else "English"
    prompt = f"""
Translate each news headline into {target_language}.

Rules:
- Preserve names, places, numbers, and military designations accurately.
- Do not add or remove claims.
- Keep each line concise and headline-like.
- Return one JSON object only.
- Format:
  {{
    "translations": [
      {{"index": 0, "text": "..."}}
    ]
  }}

Headlines:
{json.dumps(titles, ensure_ascii=False, indent=2)}
""".strip()
    payload = run_structured_prompt(prompt, model=model)
    translated = [""] * len(titles)
    for row in payload.get("translations", []):
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(titles):
            translated[index] = str(row.get("text", "")).strip()
    return tuple(translated)


def translate_news_titles(
    titles: List[str],
    language: str,
    model: Optional[str] = None,
) -> List[str]:
    if not titles:
        return []
    translations = list(
        _translate_title_batch_cached(
            language,
            json.dumps(titles, ensure_ascii=False),
            model,
        )
    )
    return [
        translations[index] if index < len(translations) and translations[index] else title
        for index, title in enumerate(titles)
    ]


@lru_cache(maxsize=256)
def _translate_brief_texts_cached(
    language: str,
    texts_json: str,
    model: Optional[str],
) -> tuple[str, ...]:
    texts = json.loads(texts_json)
    if not texts:
        return tuple()
    target_language = "Simplified Chinese" if language == "zh" else "English"
    prompt = f"""
Translate each short analytical note into {target_language}.

Rules:
- Preserve names, places, numbers, and military designations accurately.
- Keep the tone concise and analytical.
- Return one JSON object only.
- Format:
  {{
    "translations": [
      {{"index": 0, "text": "..."}}
    ]
  }}

Notes:
{json.dumps(texts, ensure_ascii=False, indent=2)}
""".strip()
    payload = run_structured_prompt(prompt, model=model)
    translated = [""] * len(texts)
    for row in payload.get("translations", []):
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(texts):
            translated[index] = str(row.get("text", "")).strip()
    return tuple(translated)


def translate_brief_texts(
    texts: List[str],
    language: str,
    model: Optional[str] = None,
) -> List[str]:
    if not texts:
        return []
    translations = list(
        _translate_brief_texts_cached(
            language,
            json.dumps(texts, ensure_ascii=False),
            model,
        )
    )
    return [
        translations[index] if index < len(translations) and translations[index] else text
        for index, text in enumerate(texts)
    ]


@lru_cache(maxsize=128)
def _assess_event_relevance_cached(
    language: str,
    events_json: str,
    model: Optional[str],
) -> tuple[dict[str, Any], ...]:
    events = json.loads(events_json)
    if not events:
        return tuple()
    target_language = "Simplified Chinese" if language == "zh" else "English"
    prompt = f"""
You are scoring events for an Iran conflict decision dashboard.

For each event, decide whether it is directly relevant to forecasting:
- war end timing
- likely outcome
- regional spillover
- official military escalation or de-escalation
- shipping and energy disruption
- leadership stability
- negotiations, mediation, or external involvement

Reject routine commentary, generic opinion, duplicate noise, and low-consequence items.

Return one JSON object only.
Format:
{{
  "assessments": [
    {{
      "index": 0,
      "decision_related": true,
      "score": 0.0,
      "reason": "short explanation in {target_language}",
      "summary": "brief summary in {target_language}"
    }}
  ]
}}

Rules:
- `score` is between 0 and 1.
- `reason` must be short, concrete, and explain why the event matters for a decision-maker.
- `summary` must be factual, concise, and no longer than 200 characters.
- `summary` must add substantive information beyond the title.
- Do not simply restate the market question or headline.
- Include at least one concrete detail not obvious from the title when available:
  probability, price move, 24h volume, liquidity, place, actor, date, asset hit, shipping effect, or official response.
- Target length:
  60-180 Chinese characters for Simplified Chinese;
  90-220 characters for English.
- If the body is sparse, summarize the strongest supporting detail from the supplied fields instead of repeating the title.
- Do not invent facts beyond the provided event fields.

Events:
{json.dumps(events, ensure_ascii=False, indent=2)}
""".strip()
    payload = run_structured_prompt(prompt, model=model)
    results: List[dict[str, Any]] = []
    for row in payload.get("assessments", []):
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        results.append(
            {
                "index": index,
                "decision_related": bool(row.get("decision_related")),
                "score": max(0.0, min(1.0, float(row.get("score", 0.0) or 0.0))),
                "reason": str(row.get("reason", "")).strip(),
                "summary": str(row.get("summary", "")).strip(),
            }
        )
    return tuple(results)


def assess_event_relevance(
    events: List[Dict[str, Any]],
    language: str,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not events:
        return []
    compact_events = [
        {
            "index": index,
            "title": str(event.get("title", "")),
            "source": str(event.get("source", "")),
            "published_at": str(event.get("published_at") or event.get("fetched_at") or ""),
            "content": _build_event_context(event),
            "credibility": event.get("credibility"),
            "importance": event.get("importance"),
            "market_volume": event.get("market_volume"),
            "market_volume_24h": event.get("market_volume_24h"),
            "market_liquidity": event.get("market_liquidity"),
        }
        for index, event in enumerate(events)
    ]
    assessments = _assess_event_relevance_cached(
        language,
        json.dumps(compact_events, ensure_ascii=False),
        model,
    )
    mapped = {
        int(row["index"]): {
            "decision_related": bool(row.get("decision_related")),
            "relevance_score": float(row.get("score", 0.0)),
            "relevance_reason": str(row.get("reason", "")).strip(),
            "brief_summary": str(row.get("summary", "")).strip(),
        }
        for row in assessments
    }
    return [
        {
            **event,
            **mapped.get(
                index,
                {"decision_related": False, "relevance_score": 0.0, "relevance_reason": "", "brief_summary": ""},
            ),
            "brief_summary": stabilize_event_summary(
                {
                    **event,
                    **mapped.get(index, {}),
                },
                language=language,
            ),
        }
        for index, event in enumerate(events)
    ]
