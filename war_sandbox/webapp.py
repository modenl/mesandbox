import json
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .service import SandboxService
from .war_state import SOURCE_STACK


TEXT = {
    "zh": {
        "lang_code": "zh-CN",
        "title": "伊朗战局沙盘推演台",
        "subtitle": "面向研判与决策的实时战局评估与终局预判。",
        "menu": "系统菜单",
        "overview": "总览",
        "end_time": "结束时间窗口",
        "prediction": "结果预判",
        "confidence_value": "置信度",
        "important_news": "重要新闻筛选",
        "news_empty": "当前没有满足“高可信 + 高战略价值”的事件。",
        "news_window_note": "仅展示最近7天内、经模型判定与结束时间或结果预判直接相关的信息。",
        "news_relevance": "为何相关",
        "news_relevance_score": "相关性分",
        "latest_forecast": "最新推演",
        "latest_forecast_time": "最新推演时间",
        "evidence_items": "证据条目",
        "tension_index": "紧张指数",
        "composite_confidence": "综合置信度",
        "run_forecast_now": "立即推演",
        "all_sources": "全部数据源",
        "source_name": "名称",
        "source_kind": "类型",
        "last_run": "最近运行",
        "status": "状态",
        "message": "消息",
        "last_items": "最近入库",
        "interval": "更新间隔",
        "manual": "手动执行",
        "save": "保存",
        "enabled": "启用",
        "run_now": "立即运行",
        "outcomes": "结果概率",
        "successors": "继任政府场景",
        "recent": "最近推演",
        "report": "推演报告",
        "scenario": "场景",
        "probability": "概率",
        "rationale": "依据",
        "name": "名称",
        "lead_figures": "关键人物",
        "architecture": "治理架构",
        "first_180_days": "前180天政策",
        "created": "生成时间",
        "hours": "证据窗口",
        "model": "模型",
        "as_of": "截至",
        "confidence": "置信说明",
        "no_forecast": "暂无推演结果",
        "menu_lang": "界面语言",
        "menu_schedule": "自动推演间隔（秒）",
        "menu_refresh": "页面刷新间隔（秒）",
        "menu_hours": "证据窗口（小时）",
        "menu_limit": "推演样本上限",
        "menu_auto": "自动推演",
        "menu_save": "保存菜单设置",
        "language_zh": "中文",
        "language_en": "English",
        "kind_gdelt": "新闻检索",
        "kind_reliefweb": "人道报告",
        "kind_rss": "RSS 订阅",
        "status_ok": "正常",
        "status_error": "错误",
        "status_unknown": "未运行",
        "status_blocked": "未配置",
        "open_menu": "展开",
        "close_menu": "收起",
        "watchlist": "重点观察",
        "decision_panel": "伊朗战争终局面板",
        "decision_panel_subtitle": "只显示当前阶段、结束窗口、最可能结局、决定性信号和最大不确定性。",
        "current_war_state": "当前战争状态",
        "end_window_box": "高强度阶段结束窗口",
        "most_likely_outcome_box": "最可能结局",
        "decisive_signals_box": "前5个决定性信号",
        "uncertainty_box": "最大不确定性",
        "signal_stack": "固定信号栈",
        "signal_stack_subtitle": "固定为 8 类免费信号源。状态机只吃高可信、高战略价值事件。",
        "runtime_panel": "采集运行状态",
        "advanced_outputs": "高级输出",
        "advanced_outputs_subtitle": "完整概率表、继任情景、历史记录和原始报告收进折叠区，避免干扰主判断。",
        "source_stack_live": "实时接入",
        "source_stack_gap": "待接入",
        "reasoning_flow": "推导因果流程图",
        "flow_hint": "点击任意节点，查看当前这一轮推演实际带入的数据、评估和公式。",
        "detail_panel": "节点详情",
        "detail_summary": "当前结论",
        "detail_metrics": "当前指标",
        "detail_inputs": "当前带入信息",
        "detail_assessment": "当前评估",
        "detail_formula": "置信度公式",
        "score": "分数",
        "window": "时间窗",
        "formula_caption": "系统把置信度拆成 5 个显式变量，再按固定权重加总。",
        "no_graph": "暂无可展示的推导流程，请先运行一次推演。",
        "node_click": "点击查看",
        "tier": "等级",
        "news_default": "默认展示最近 20 条有用信息，可切换查看更多。",
        "news_show": "显示条数",
        "news_visible": "当前显示",
        "news_all": "全部",
        "sources_in_use": "信息源状态",
        "sources_in_use_note": "只展示当前真实接入的数据源。绿点表示当前抓取可用，其它状态表示暂不可用或已停用。",
        "source_why_trust": "为何可信",
        "source_status": "当前状态",
        "source_last_run": "最近抓取",
        "source_last_items": "最近入库",
        "source_availability_ok": "可用",
        "source_availability_issue": "异常",
        "source_availability_idle": "未就绪",
    },
    "en": {
        "lang_code": "en",
        "title": "Iran Conflict Decision Dashboard",
        "subtitle": "Real-time conflict assessment and endgame forecasting for decision support.",
        "menu": "System Menu",
        "overview": "Overview",
        "end_time": "End Window",
        "prediction": "Outcome Call",
        "confidence_value": "Confidence",
        "important_news": "Important Filtered News",
        "news_empty": "No event currently passes the high-credibility and high-strategic-value filter.",
        "news_window_note": "Only items from the last 7 days are shown, and each item must be judged by the model as directly relevant to end timing or likely outcome.",
        "news_relevance": "Why it matters",
        "news_relevance_score": "Relevance score",
        "latest_forecast": "Latest Forecast",
        "latest_forecast_time": "Latest forecast time",
        "evidence_items": "Evidence items",
        "tension_index": "Tension index",
        "composite_confidence": "Composite confidence",
        "run_forecast_now": "Run forecast now",
        "all_sources": "All Data Sources",
        "source_name": "Name",
        "source_kind": "Kind",
        "last_run": "Last run",
        "status": "Status",
        "message": "Message",
        "last_items": "Last items",
        "interval": "Update interval",
        "manual": "Manual",
        "save": "Save",
        "enabled": "Enabled",
        "run_now": "Run now",
        "outcomes": "Outcome Probabilities",
        "successors": "Successor Government Scenarios",
        "recent": "Recent Forecasts",
        "report": "Report",
        "scenario": "Scenario",
        "probability": "Probability",
        "rationale": "Rationale",
        "name": "Name",
        "lead_figures": "Lead Figures",
        "architecture": "Architecture",
        "first_180_days": "First 180 Days",
        "created": "Created",
        "hours": "Hours",
        "model": "Model",
        "as_of": "As of",
        "confidence": "Confidence",
        "no_forecast": "No forecast available.",
        "menu_lang": "Interface language",
        "menu_schedule": "Auto forecast interval (seconds)",
        "menu_refresh": "Page refresh interval (seconds)",
        "menu_hours": "Evidence window (hours)",
        "menu_limit": "Forecast item limit",
        "menu_auto": "Auto forecast",
        "menu_save": "Save menu settings",
        "language_zh": "中文",
        "language_en": "English",
        "kind_gdelt": "News Search",
        "kind_reliefweb": "Humanitarian Reports",
        "kind_rss": "RSS Feed",
        "status_ok": "OK",
        "status_error": "Error",
        "status_unknown": "Not run",
        "status_blocked": "Not configured",
        "open_menu": "Open",
        "close_menu": "Close",
        "watchlist": "Watchlist",
        "decision_panel": "Iran War Endgame Panel",
        "decision_panel_subtitle": "Shows only the current phase, termination windows, top outcome, decisive signals, and biggest uncertainty.",
        "current_war_state": "Current war state",
        "end_window_box": "High-intensity end window",
        "most_likely_outcome_box": "Most likely outcome",
        "decisive_signals_box": "Top 5 decisive signals",
        "uncertainty_box": "Biggest uncertainty",
        "signal_stack": "Fixed Signal Stack",
        "signal_stack_subtitle": "Fixed to 8 free signal categories. The state machine only consumes high-credibility, high-strategic-value events.",
        "runtime_panel": "Collection Runtime",
        "advanced_outputs": "Advanced Outputs",
        "advanced_outputs_subtitle": "Full probability tables, successor scenarios, history, and the raw report are folded away so they do not crowd the main judgment.",
        "source_stack_live": "Live",
        "source_stack_gap": "Planned",
        "reasoning_flow": "Interactive Causal Flow",
        "flow_hint": "Click any node to inspect the live inputs, evaluation, and formula used in this run.",
        "detail_panel": "Node Detail",
        "detail_summary": "Current conclusion",
        "detail_metrics": "Current metrics",
        "detail_inputs": "Current inputs",
        "detail_assessment": "Current assessment",
        "detail_formula": "Confidence formula",
        "score": "Score",
        "window": "Window",
        "formula_caption": "Confidence is decomposed into 5 explicit variables and combined with fixed weights.",
        "no_graph": "No reasoning graph available yet. Run a forecast first.",
        "node_click": "Click to inspect",
        "tier": "Tier",
        "news_default": "Shows the latest 20 useful items by default. Expand the count to see more.",
        "news_show": "Show",
        "news_visible": "Visible",
        "news_all": "All",
        "sources_in_use": "Source Status",
        "sources_in_use_note": "This list shows only live configured sources. A green dot means the current fetch path is working; other states mean it is unavailable or disabled.",
        "source_why_trust": "Why it is trusted",
        "source_status": "Current status",
        "source_last_run": "Last fetch",
        "source_last_items": "Last inserted",
        "source_availability_ok": "Available",
        "source_availability_issue": "Issue",
        "source_availability_idle": "Idle",
    },
}


SOURCE_BRIEFS = {
    "gdelt_articles": {
        "zh": "GDELT 聚合跨媒体新近报道，适合发现刚出现的战局变化，但需要和官方源交叉验证。",
        "en": "GDELT aggregates fresh multi-outlet reporting and is useful for detecting newly emerging shifts, but should be cross-checked with official sources.",
    },
    "gdelt_timeline": {
        "zh": "GDELT 时间序列适合衡量事件热度和舆情强度变化，价值在于趋势，不在于单条事实。",
        "en": "GDELT timeline data is useful for tracking event intensity and attention shifts; its value is directional trend, not single-claim fact reporting.",
    },
    "liveuamap_iran": {
        "zh": "LiveUAmap 提供接近实时的地理化冲突线索，适合捕捉地点和时间，但需防止单源误报。",
        "en": "LiveUAmap offers near-real-time geolocated conflict cues, useful for place-and-time awareness, but it should not stand alone.",
    },
    "centcom_dvids": {
        "zh": "CENTCOM 官方发布代表美方正式口径，可信度高，尤其适合判断目标边界和行动声明。",
        "en": "CENTCOM releases represent official U.S. messaging and are high-value for judging stated objectives, target scope, and declared operations.",
    },
    "idf_releases": {
        "zh": "IDF 官方发布是以方正式口径，适合判断军事行动声明、打击对象和阶段转换。",
        "en": "IDF releases are official Israeli statements and are useful for tracking declared operations, target sets, and shifts in operational phase.",
    },
    "presstv_latest": {
        "zh": "PressTV 反映伊朗叙事与对外表述，适合观察伊朗侧公开口径和升级/谈判信号。",
        "en": "PressTV reflects Iranian public-facing narrative and is useful for tracking Tehran-aligned messaging, escalation signals, and negotiation framing.",
    },
    "radiofarda_iran": {
        "zh": "Radio Farda 提供与伊朗内部政治和社会动向相关的补充观察，适合识别国内不稳定信号。",
        "en": "Radio Farda adds useful coverage of internal Iranian political and social developments, especially for domestic instability signals.",
    },
    "unnews_middle_east": {
        "zh": "联合国新闻在措辞上更克制，适合补充地区安全与人道后果的国际机构视角。",
        "en": "UN News is more restrained in tone and is useful for adding an international institutional view on regional security and humanitarian impact.",
    },
    "unnews_peace_security": {
        "zh": "联合国和平与安全频道适合识别斡旋、停火和安理会层面的正式动向。",
        "en": "UN Peace and Security coverage is useful for detecting mediation, ceasefire, and formal Security Council-level developments.",
    },
    "iaea_news": {
        "zh": "IAEA 是核议题的一手机构源，涉及核设施、核监督和相关风险时参考价值高。",
        "en": "IAEA is a primary institutional source on nuclear issues and is especially valuable for facilities, safeguards, and related escalation risk.",
    },
    "adsb_military": {
        "zh": "ADSB 军机数据属于传感器类硬信号，适合发现空中加油、预警和军机活动异常。",
        "en": "ADSB military traffic is a sensor-grade hard signal, useful for spotting tanker, AWACS, and abnormal air-activity patterns.",
    },
    "oil_market": {
        "zh": "国际原油期货价格是最直接的外溢成本信号之一，能快速反映霍尔木兹、油运和地区升级风险。",
        "en": "International crude futures are one of the hardest spillover signals, reacting quickly to Hormuz, tanker disruption, and regional escalation risk.",
    },
    "polymarket_geopolitics": {
        "zh": "Polymarket 反映真实资金下注形成的隐含概率，适合观察市场如何定价领导人变动、停火或升级预期。",
        "en": "Polymarket reflects implied probabilities backed by real-money positioning, which is useful for tracking how markets price leadership changes, ceasefire odds, and escalation risk.",
    },
    "google_news_iran_conflict": {
        "zh": "Google News 作为聚合入口有助于补足多家媒体首发覆盖，但必须依赖后续筛选和去重。",
        "en": "Google News is a useful aggregator for broad first-wave coverage, but it only becomes reliable after filtering, deduping, and source weighting.",
    },
    "google_news_hormuz_shipping": {
        "zh": "霍尔木兹航运聚合流用于补捉海运与能源外溢信号，重点看是否影响通航与油运节奏。",
        "en": "The Hormuz shipping news stream is used to track maritime and energy spillover, especially whether transit and tanker flows are being disrupted.",
    },
}


FLOW_LAYOUT = {
    "source_intake": {"x": 360, "y": 28},
    "evidence_base": {"x": 360, "y": 146},
    "signal_extraction": {"x": 360, "y": 264},
    "causal_assessment": {"x": 360, "y": 382},
    "scenario_engine": {"x": 360, "y": 500},
    "termination_projection": {"x": 96, "y": 676},
    "succession_projection": {"x": 624, "y": 676},
    "confidence_calibration": {"x": 360, "y": 812},
}


def _listify(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [str(value)]


def _availability_meta(source: dict, text: dict) -> tuple[str, str]:
    if not source.get("enabled", True):
        return "dot-idle", text["source_availability_idle"]
    status = source.get("last_status")
    if status == "ok":
        return "dot-ok", text["source_availability_ok"]
    if status in {"error", "blocked"}:
        return "dot-issue", text["source_availability_issue"]
    return "dot-idle", text["source_availability_idle"]


def _source_brief_section(runtime_sources: list[dict], text: dict, language: str) -> str:
    if not runtime_sources:
        return ""
    stack_by_id = {str(item.get("id", "")): item for item in SOURCE_STACK}
    status_order = {"ok": 0, "error": 1, "blocked": 2, None: 3}
    cards = []
    for runtime in sorted(
        runtime_sources,
        key=lambda source: (
            1 if not source.get("enabled", True) else 0,
            status_order.get(source.get("last_status"), 3),
            str(source.get("name", "")).lower(),
        ),
    ):
        source_id = str(runtime.get("id", ""))
        stack = stack_by_id.get(source_id, {})
        brief = SOURCE_BRIEFS.get(source_id, {}).get(language) or ""
        dot_class, availability = _availability_meta(runtime, text)
        status_text = _status_text(text, runtime.get("last_status"))
        message = str(runtime.get("last_message") or "-")
        cards.append(
            f"""
            <article class="source-brief">
              <div class="source-brief-top">
                <div>
                  <div class="source-brief-name">{escape(str(runtime.get('name') or stack.get('name') or source_id))}</div>
                  <div class="source-brief-id">{escape(source_id)}</div>
                </div>
                <div class="source-availability">
                  <span class="source-dot {dot_class}"></span>
                  <span>{escape(availability)}</span>
                </div>
              </div>
              <p class="source-brief-copy"><strong>{escape(text['source_why_trust'])}:</strong> {escape(brief or '-')}</p>
              <p class="source-brief-copy"><strong>{escape(text['source_status'])}:</strong> {escape(status_text)} · {escape(message)}</p>
              <p class="source-brief-copy"><strong>{escape(text['source_last_run'])}:</strong> {escape(str(runtime.get('last_run_at') or '-'))} · <strong>{escape(text['source_last_items'])}:</strong> {escape(str(runtime.get('last_item_count', 0)))}</p>
            </article>
            """
        )
    return f"""
      <details class="card fold-card">
        <summary>
          <span class="section-title">{escape(text['sources_in_use'])}</span>
          <span class="compact-note">{escape(text['open_menu'])} / {escape(text['close_menu'])}</span>
        </summary>
        <p class="compact-note">{escape(text['sources_in_use_note'])}</p>
        <div class="source-brief-grid">
          {''.join(cards)}
        </div>
      </details>
    """


def _news_section(top_events: list[dict], text: dict) -> str:
    total = len(top_events)
    if total == 0:
        return f"<div class='empty'>{escape(text['news_empty'])}</div>"

    options = [
        (20, "20"),
        (30, "30"),
        (50, "50"),
        (9999, text["news_all"]),
    ]
    option_rows = "".join(
        f"<option value='{value}' {'selected' if value == 20 else ''}>{escape(label)}</option>"
        for value, label in options
        if value == 9999 or value <= max(20, total)
    )
    news_rows = "".join(
        f"""
        <a class="news-item" data-news-item href="{escape(item.get('url', '#'))}" target="_blank" rel="noopener">
          <div class="news-head">
            <span class="news-source">{escape(str(item.get('source', '-')))}</span>
            <span class="news-time">{escape(str(item.get('published_at') or item.get('fetched_at') or '-'))}</span>
          </div>
          <h3>{escape(str(item.get('title', '-')))}</h3>
          <p class="news-reason"><strong>{escape(text['news_relevance'])}:</strong> {escape(str(item.get('relevance_reason') or '-'))}</p>
          <div class="news-meta">
            <span>C {escape(str(item.get('credibility', '-')))}</span>
            <span>I {escape(str(item.get('importance', '-')))}</span>
            <span>{escape(text['news_relevance_score'])} {escape(str(item.get('relevance_score', '-')))}</span>
          </div>
        </a>
        """
        for item in top_events
    )
    return f"""
    <div class="news-toolbar">
      <p class="compact-note">{escape(text['news_window_note'])}</p>
      <label class="news-control">
        <span>{escape(text['news_show'])}</span>
        <select id="news-count-select">{option_rows}</select>
      </label>
      <div class="compact-note">{escape(text['news_visible'])}: <strong id="news-visible-count">0 / {total}</strong></div>
    </div>
    <div class="news-grid">{news_rows}</div>
    <script>
      (() => {{
        const select = document.getElementById("news-count-select");
        const counter = document.getElementById("news-visible-count");
        const items = Array.from(document.querySelectorAll("[data-news-item]"));
        if (!select || !counter || !items.length) return;
        try {{
          const saved = localStorage.getItem("mesim-news-count");
          if (saved && Array.from(select.options).some((option) => option.value === saved)) {{
            select.value = saved;
          }}
        }} catch (_error) {{}}
        const apply = () => {{
          const raw = Number.parseInt(select.value, 10) || 20;
          const visible = raw >= 9999 ? items.length : Math.min(raw, items.length);
          items.forEach((item, index) => {{
            item.style.display = index < visible ? "block" : "none";
          }});
          counter.textContent = `${{visible}} / {total}`;
          try {{
            localStorage.setItem("mesim-news-count", String(raw));
          }} catch (_error) {{}}
        }};
        select.addEventListener("change", apply);
        apply();
      }})();
    </script>
    """


def _status_text(text: dict, value: Optional[str]) -> str:
    if value == "ok":
        return text["status_ok"]
    if value == "error":
        return text["status_error"]
    if value == "blocked":
        return text["status_blocked"]
    return text["status_unknown"]


def _kind_text(text: dict, kind: str) -> str:
    return text.get(f"kind_{kind}", kind)


def _source_rows(sources: list[dict], text: dict) -> str:
    rows = []
    for source in sources:
        checked = "checked" if source["enabled"] else ""
        status = _status_text(text, source.get("last_status"))
        status_class = f"status-{source.get('last_status') or 'idle'}"
        rows.append(
            f"""
            <tr>
              <td>
                <div class="source-name">{escape(source['name'])}</div>
                <div class="source-id">{escape(source['id'])}</div>
              </td>
              <td>{escape(_kind_text(text, source['kind']))}</td>
              <td>{escape(str(source.get('last_run_at') or '-'))}</td>
              <td><span class="status-pill {status_class}">{escape(status)}</span></td>
              <td class="message-cell">{escape(str(source.get('last_message') or '-'))}</td>
              <td>{escape(str(source.get('last_item_count', 0)))}</td>
              <td>
                <form class="inline-form" method="post" action="/source/update">
                  <input type="hidden" name="source_id" value="{escape(source['id'])}">
                  <label class="switch-row">
                    <input type="checkbox" name="enabled" value="1" {checked}>
                    <span>{text['enabled']}</span>
                  </label>
                  <input type="number" min="60" step="60" name="interval_seconds" value="{int(source['interval_seconds'])}">
                  <button type="submit">{text['save']}</button>
                </form>
              </td>
              <td>
                <form method="post" action="/source/run">
                  <input type="hidden" name="source_id" value="{escape(source['id'])}">
                  <button class="secondary-btn" type="submit">{text['run_now']}</button>
                </form>
              </td>
            </tr>
            """
        )
    return "".join(rows)


def _fallback_decision_panel(latest_forecast: dict) -> dict:
    window = latest_forecast.get("war_end_window", {})
    top_outcome = "-"
    outcomes = latest_forecast.get("outcome_probabilities", [])
    if outcomes:
        top_outcome = outcomes[0].get("scenario", "-")
    assumptions = _listify(latest_forecast.get("assumptions", []))
    return {
        "current_state": "-",
        "end_windows": [
            {"window_days": 7, "probability": window.get("p10", "-")},
            {"window_days": 14, "probability": "-"},
            {"window_days": 30, "probability": window.get("p50", "-")},
            {"window_days": 60, "probability": window.get("p90", "-")},
        ],
        "most_likely_outcome": top_outcome,
        "top_decisive_signals": [
            {"title": item}
            for item in _listify(latest_forecast.get("key_indicators_to_watch", []))[:5]
        ],
        "max_uncertainty": assumptions[:2] or ["-"],
    }


def _source_stack_rows(source_stack: list[dict], runtime_sources: list[dict], text: dict) -> str:
    runtime_by_kind = {}
    for source in runtime_sources:
        runtime_by_kind.setdefault(source.get("kind"), []).append(source)

    rows = []
    for item in source_stack:
        runtime = (runtime_by_kind.get(item.get("kind")) or [None])[0]
        live = bool(runtime)
        live_label = text["source_stack_live"] if live else text["source_stack_gap"]
        live_class = "status-ok" if live else "status-idle"
        status = _status_text(text, runtime.get("last_status") if runtime else None)
        message = runtime.get("last_message") if runtime else "-"
        rows.append(
            f"""
            <div class="stack-card">
              <div class="stack-topline">
                <span>{escape(item.get('name', '-'))}</span>
                <span class="status-pill {live_class}">{escape(live_label)}</span>
              </div>
              <div class="source-id">{escape(item.get('id', '-'))}</div>
              <div class="stack-meta">{escape(text['source_kind'])}: {escape(item.get('kind', '-'))}</div>
              <div class="stack-meta">{escape(text['status'])}: {escape(status)}</div>
              <div class="stack-meta">{escape(text['message'])}: {escape(str(message))}</div>
            </div>
            """
        )
    return "".join(rows)


def _flow_buttons(graph: dict, text: dict) -> str:
    buttons = []
    for node in graph.get("nodes", []):
        pos = FLOW_LAYOUT.get(node["id"])
        if not pos:
            continue
        buttons.append(
            f"""
            <button
              class="flow-node"
              type="button"
              data-node-id="{escape(node['id'])}"
              style="left:{pos['x']}px; top:{pos['y']}px;"
            >
              <span class="flow-node-header">
                <span class="flow-node-title">{escape(node['title'])}</span>
                <span class="flow-node-score">{escape(str(node.get('score', '-')))}</span>
              </span>
              <span class="flow-node-summary">{escape(str(node.get('summary', '')))}</span>
              <span class="flow-node-hint">{escape(text['node_click'])}</span>
            </button>
            """
        )
    return "".join(buttons)


def _flow_graph_markup(graph: dict, text: dict) -> str:
    if not graph or not graph.get("nodes"):
        return f"""
        <section class="card">
          <h2 class="section-title">{escape(text['reasoning_flow'])}</h2>
          <p class="subtitle-text">{escape(text['no_graph'])}</p>
        </section>
        """

    graph_payload = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    initial_node = "causal_assessment"
    node_ids = {node["id"] for node in graph.get("nodes", [])}
    if initial_node not in node_ids:
        initial_node = graph["nodes"][0]["id"]

    return f"""
    <section class="flow-grid">
      <div class="card flow-card">
        <div class="flow-card-head">
          <div>
            <h2 class="section-title">{escape(text['reasoning_flow'])}</h2>
            <p class="subtitle-text">{escape(text['flow_hint'])}</p>
          </div>
        </div>
        <div class="flow-stage">
          <svg class="flow-svg" viewBox="0 0 960 940" aria-hidden="true">
            <defs>
              <marker id="flow-arrow" markerWidth="10" markerHeight="10" refX="7" refY="3.5" orient="auto">
                <polygon points="0 0, 8 3.5, 0 7" fill="#6f7d76"></polygon>
              </marker>
            </defs>
            <path d="M480 112 L480 146" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M480 230 L480 264" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M480 348 L480 382" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M480 466 L480 500" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M480 588 C480 630, 290 640, 226 676" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M480 588 C480 630, 670 640, 754 676" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M226 760 C226 800, 400 796, 480 812" class="flow-path" marker-end="url(#flow-arrow)"></path>
            <path d="M754 760 C754 800, 560 796, 480 812" class="flow-path" marker-end="url(#flow-arrow)"></path>
          </svg>
          {_flow_buttons(graph, text)}
        </div>
      </div>

      <aside class="card detail-card">
        <div class="detail-topline">{escape(text['detail_panel'])}</div>
        <div class="detail-score-row">
          <div>
            <h3 id="detail-title" class="detail-title"></h3>
            <p id="detail-summary" class="detail-summary"></p>
          </div>
          <div class="detail-scorebox">
            <span>{escape(text['score'])}</span>
            <strong id="detail-score"></strong>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">{escape(text['detail_metrics'])}</div>
          <div id="detail-metrics" class="detail-metrics"></div>
        </div>

        <div class="detail-section">
          <div class="detail-label">{escape(text['detail_assessment'])}</div>
          <p id="detail-assessment" class="detail-copy"></p>
        </div>

        <div class="detail-section">
          <div class="detail-label">{escape(text['detail_inputs'])}</div>
          <ul id="detail-inputs" class="detail-list"></ul>
        </div>

        <div id="detail-formula-wrap" class="detail-section" hidden>
          <div class="detail-label">{escape(text['detail_formula'])}</div>
          <div class="formula-card">
            <code id="detail-formula"></code>
            <p class="formula-copy">{escape(text['formula_caption'])}</p>
            <ul id="detail-formula-terms" class="detail-list"></ul>
          </div>
        </div>
      </aside>
    </section>

    <script id="reasoning-graph-data" type="application/json">{graph_payload}</script>
    <script>
      (function() {{
        const dataEl = document.getElementById("reasoning-graph-data");
        if (!dataEl) return;
        const graph = JSON.parse(dataEl.textContent);
        const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
        const buttons = Array.from(document.querySelectorAll(".flow-node"));
        const titleEl = document.getElementById("detail-title");
        const summaryEl = document.getElementById("detail-summary");
        const scoreEl = document.getElementById("detail-score");
        const metricsEl = document.getElementById("detail-metrics");
        const assessmentEl = document.getElementById("detail-assessment");
        const inputsEl = document.getElementById("detail-inputs");
        const formulaWrap = document.getElementById("detail-formula-wrap");
        const formulaEl = document.getElementById("detail-formula");
        const formulaTermsEl = document.getElementById("detail-formula-terms");

        function renderMetrics(metrics) {{
          metricsEl.innerHTML = "";
          (metrics || []).forEach((metric) => {{
            const item = document.createElement("div");
            item.className = "metric-chip";
            item.innerHTML = "<span>" + metric.label + "</span><strong>" + metric.value + "</strong>";
            metricsEl.appendChild(item);
          }});
        }}

        function renderList(container, items) {{
          container.innerHTML = "";
          (items || []).forEach((item) => {{
            const li = document.createElement("li");
            li.textContent = item;
            container.appendChild(li);
          }});
        }}

        function selectNode(nodeId) {{
          const node = nodes.get(nodeId);
          if (!node) return;
          buttons.forEach((button) => {{
            button.classList.toggle("is-active", button.dataset.nodeId === nodeId);
          }});
          titleEl.textContent = node.title || "";
          summaryEl.textContent = node.summary || "";
          scoreEl.textContent = node.score ?? "";
          assessmentEl.textContent = node.assessment || "";
          renderMetrics(node.metrics);
          renderList(inputsEl, node.details);
          if (node.formula) {{
            formulaWrap.hidden = false;
            formulaEl.textContent = node.formula;
            renderList(formulaTermsEl, node.details || []);
          }} else {{
            formulaWrap.hidden = true;
            formulaEl.textContent = "";
            formulaTermsEl.innerHTML = "";
          }}
        }}

        buttons.forEach((button) => {{
          button.addEventListener("click", () => selectNode(button.dataset.nodeId));
        }});

        selectNode({json.dumps(initial_node)});
      }})();
    </script>
    """


def _html_page(state: dict) -> str:
    settings = state.get("settings", {})
    language = settings.get("language", "zh")
    text = TEXT.get(language, TEXT["zh"])
    latest = state.get("latest_forecast", {})
    refresh_seconds = int(settings.get("dashboard_refresh_seconds", 15))
    graph = state.get("reasoning_graph", {})
    latest_forecast = latest.get("forecast", {})
    latest_summary = latest.get("summary", {})
    decision_panel = latest_summary.get("decision_panel") or _fallback_decision_panel(latest_forecast)
    confidence = graph.get("confidence", {})
    window = latest_forecast.get("war_end_window", {})
    source_brief_section = _source_brief_section(state.get("sources", []), text, language)
    end_windows = "".join(
        f"<div class='mini-row'><span>{escape(str(item.get('window_days')))}d</span><strong>{escape(str(item.get('probability')))}</strong></div>"
        for item in decision_panel.get("end_windows", [])
    )
    top_events = latest_summary.get("top_events", [])
    news_section = _news_section(top_events, text)

    return f"""<!doctype html>
<html lang="{escape(text['lang_code'])}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <title>{escape(text['title'])}</title>
  <style>
    :root {{
      --bg: #edf1ea;
      --panel: rgba(252, 250, 245, 0.95);
      --ink: #16201f;
      --muted: #68726d;
      --line: rgba(26, 42, 39, 0.12);
      --accent: #0f5c4d;
      --shadow: 0 16px 36px rgba(22, 32, 31, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f4f6f1 0%, var(--bg) 100%);
    }}
    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .brand {{
      max-width: 760px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(15, 92, 77, 0.08);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 12px 0 8px;
      font-size: clamp(30px, 5vw, 46px);
      line-height: 1.04;
      letter-spacing: -0.03em;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.6;
    }}
    details.menu {{
      width: min(360px, 100%);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: rgba(251, 248, 241, 0.86);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    details.menu summary {{
      list-style: none;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 18px;
      font-weight: 700;
    }}
    details.menu summary::-webkit-details-marker {{ display: none; }}
    details.fold-card summary::-webkit-details-marker {{ display: none; }}
    .menu-body {{
      border-top: 1px solid var(--line);
      padding: 18px;
      display: grid;
      gap: 14px;
    }}
    .menu-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .field {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .field input, .field select {{
      width: 100%;
      border: 1px solid var(--line);
      background: white;
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
      color: var(--ink);
    }}
    .menu-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .dashboard {{
      display: grid;
      gap: 20px;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 20px;
    }}
    .fold-card {{
      padding: 0 20px 20px;
    }}
    .fold-card summary {{
      list-style: none;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 0 16px;
    }}
    .section-title {{
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .stat-label {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .stat-value {{
      margin-top: 8px;
      font-size: clamp(22px, 3vw, 30px);
      font-weight: 800;
      letter-spacing: -0.03em;
      word-break: break-word;
    }}
    .window-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .window-chip {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
    }}
    .window-chip strong {{
      display: block;
      margin-top: 6px;
      font-size: 20px;
      letter-spacing: -0.03em;
    }}
    .compact-copy {{
      display: grid;
      gap: 10px;
      margin-top: 18px;
    }}
    button {{
      border: 0;
      background: var(--accent);
      color: white;
      border-radius: 999px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
      font: inherit;
    }}
    .secondary-btn {{
      background: rgba(15, 92, 77, 0.12);
      color: var(--accent);
    }}
    .mini-grid {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}
    .mini-row {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(15, 92, 77, 0.06);
      border: 1px solid rgba(15, 92, 77, 0.08);
    }}
    .news-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .source-brief-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .source-brief {{
      border: 1px solid rgba(15, 92, 77, 0.1);
      border-radius: 16px;
      padding: 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(15, 92, 77, 0.03));
    }}
    .source-brief-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 10px;
    }}
    .source-brief-name {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .source-brief-id, .source-brief-count {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .source-brief-copy {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    .source-availability {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .source-dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .dot-ok {{ background: #1f9f58; box-shadow: 0 0 0 4px rgba(31, 159, 88, 0.12); }}
    .dot-issue {{ background: #d66a1f; box-shadow: 0 0 0 4px rgba(214, 106, 31, 0.12); }}
    .dot-idle {{ background: #9aa39f; box-shadow: 0 0 0 4px rgba(154, 163, 159, 0.14); }}
    .news-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .news-control {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
    }}
    .news-control select {{
      border: 1px solid var(--line);
      background: white;
      border-radius: 999px;
      padding: 8px 12px;
      font: inherit;
      color: var(--ink);
    }}
    .news-item {{
      text-decoration: none;
      color: inherit;
      display: block;
      background: linear-gradient(180deg, rgba(15, 92, 77, 0.06), rgba(15, 92, 77, 0.02));
      border: 1px solid rgba(15, 92, 77, 0.1);
      border-radius: 16px;
      padding: 16px;
    }}
    .news-item h3 {{
      margin: 10px 0;
      font-size: 18px;
      line-height: 1.45;
    }}
    .news-reason {{
      margin: 0 0 12px;
      color: var(--ink);
      font-size: 14px;
      line-height: 1.6;
    }}
    .news-head, .news-meta {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .compact-note {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    @media (max-width: 960px) {{
      .topbar {{
        flex-direction: column;
      }}
      details.menu {{
        width: 100%;
      }}
      .summary-grid, .window-grid, .menu-grid, .news-grid, .source-brief-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .shell {{
        padding: 16px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div class="brand">
        <div class="eyebrow">Decision Dashboard</div>
        <h1>{escape(text['title'])}</h1>
        <p class="subtitle">{escape(text['subtitle'])}</p>
      </div>
      <details class="menu">
        <summary>
          <span>{escape(text['menu'])}</span>
          <span>{escape(text['open_menu'])} / {escape(text['close_menu'])}</span>
        </summary>
        <div class="menu-body">
          <form method="post" action="/settings/update">
            <div class="menu-grid">
              <label class="field">
                <span>{escape(text['menu_lang'])}</span>
                <select name="language">
                  <option value="zh" {'selected' if language == 'zh' else ''}>{escape(text['language_zh'])}</option>
                  <option value="en" {'selected' if language == 'en' else ''}>{escape(text['language_en'])}</option>
                </select>
              </label>
              <label class="field">
                <span>{escape(text['menu_schedule'])}</span>
                <input type="number" min="60" step="60" name="forecast_interval_seconds" value="{int(settings.get('forecast_interval_seconds', 1800))}">
              </label>
              <label class="field">
                <span>{escape(text['menu_refresh'])}</span>
                <input type="number" min="5" step="1" name="dashboard_refresh_seconds" value="{refresh_seconds}">
              </label>
              <label class="field">
                <span>{escape(text['menu_limit'])}</span>
                <input type="number" min="50" step="10" name="forecast_limit" value="{int(settings.get('forecast_limit', 200))}">
              </label>
              <label class="field">
                <span>{escape(text['menu_auto'])}</span>
                <select name="auto_forecast">
                  <option value="1" {'selected' if settings.get('auto_forecast', True) else ''}>ON</option>
                  <option value="0" {'selected' if not settings.get('auto_forecast', True) else ''}>OFF</option>
                </select>
              </label>
            </div>
            <div class="menu-actions">
              <button type="submit">{escape(text['menu_save'])}</button>
            </div>
          </form>
        </div>
      </details>
    </div>

    <div class="dashboard">
      <section class="summary-grid">
        <div class="card">
          <div class="stat-label">{escape(text['end_time'])}</div>
          <div class="stat-value">{escape(str(window.get('p50', '-')))}</div>
          <div class="window-grid">
            <div class="window-chip">P10<strong>{escape(str(window.get('p10', '-')))}</strong></div>
            <div class="window-chip">P50<strong>{escape(str(window.get('p50', '-')))}</strong></div>
            <div class="window-chip">P90<strong>{escape(str(window.get('p90', '-')))}</strong></div>
          </div>
          <div class="mini-grid">{end_windows}</div>
          <div class="compact-copy">
            <div class="compact-note">{escape(text['latest_forecast_time'])}: {escape(str(latest.get('created_at', '-')))}</div>
          </div>
        </div>

        <div class="card">
          <div class="stat-label">{escape(text['prediction'])}</div>
          <div class="stat-value">{escape(str(decision_panel.get('most_likely_outcome', '-')))}</div>
          <div class="compact-copy">
            <div class="compact-note">{escape(text['current_war_state'])}: {escape(str(decision_panel.get('current_state', '-')))}</div>
            <div class="compact-note">{escape(text['evidence_items'])}: {escape(str(latest_summary.get('item_count', 0)))}</div>
            <div class="compact-note">{escape(text['tension_index'])}: {escape(str(latest_summary.get('tension_index', '-')))}</div>
          </div>
        </div>

        <div class="card">
          <div class="stat-label">{escape(text['confidence_value'])}</div>
          <div class="stat-value">{escape(str(confidence.get('score', '-')))}</div>
          <div class="compact-copy">
            <div class="compact-note">{escape(text['tier'])}: {escape(str(confidence.get('tier', '-')))}</div>
            <div class="compact-note">{escape(text['confidence'])}: {escape(str(latest_forecast.get('confidence_note', '-')))}</div>
          </div>
          <form method="post" action="/forecast/run">
              <button type="submit">{escape(text['run_forecast_now'])}</button>
          </form>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">{escape(text['important_news'])}</h2>
        {news_section}
      </section>

      {source_brief_section}
    </div>
  </div>
</body>
</html>
"""


def render_static_snapshot(state: dict) -> str:
    settings = state.get("settings", {})
    language = settings.get("language", "zh")
    text = TEXT.get(language, TEXT["zh"])
    latest = state.get("latest_forecast", {})
    latest_forecast = latest.get("forecast", {})
    latest_summary = latest.get("summary", {})
    decision_panel = latest_summary.get("decision_panel") or _fallback_decision_panel(latest_forecast)
    graph = state.get("reasoning_graph", {})
    confidence = graph.get("confidence", {})
    window = latest_forecast.get("war_end_window", {})
    top_events = latest_summary.get("top_events", [])
    updated_at = latest.get("created_at") or latest_summary.get("generated_at") or "-"
    source_brief_section = _source_brief_section(state.get("sources", []), text, language)

    end_windows = "".join(
        f"<div class='mini-row'><span>{escape(str(item.get('window_days')))}d</span><strong>{escape(str(item.get('probability')))}</strong></div>"
        for item in decision_panel.get("end_windows", [])
    )
    news_section = _news_section(top_events, text)

    return f"""<!doctype html>
<html lang="{escape(text['lang_code'])}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(text['title'])}</title>
  <style>
    :root {{
      --bg: #edf1ea;
      --panel: rgba(252, 250, 245, 0.95);
      --ink: #16201f;
      --muted: #68726d;
      --line: rgba(26, 42, 39, 0.12);
      --accent: #0f5c4d;
      --shadow: 0 16px 36px rgba(22, 32, 31, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f4f6f1 0%, var(--bg) 100%);
    }}
    .shell {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .eyebrow {{
      display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px;
      background: rgba(15, 92, 77, 0.08); color: var(--accent); font-size: 12px; font-weight: 700;
      letter-spacing: 0.08em; text-transform: uppercase;
    }}
    h1 {{ margin: 12px 0 8px; font-size: clamp(30px, 5vw, 46px); line-height: 1.04; letter-spacing: -0.03em; }}
    .subtitle, .compact-note {{ color: var(--muted); line-height: 1.6; font-size: 14px; }}
    .dashboard {{ display: grid; gap: 20px; margin-top: 18px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
    .card {{
      background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
      box-shadow: var(--shadow); padding: 20px;
    }}
    .fold-card {{ padding: 0 20px 20px; }}
    .fold-card summary {{
      list-style: none; cursor: pointer; display: flex; justify-content: space-between;
      align-items: center; padding: 20px 0 16px;
    }}
    .fold-card summary::-webkit-details-marker {{ display: none; }}
    .section-title {{ margin: 0 0 14px; font-size: 18px; letter-spacing: -0.02em; }}
    .stat-label {{
      font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em;
    }}
    .stat-value {{
      margin-top: 8px; font-size: clamp(22px, 3vw, 30px); font-weight: 800; letter-spacing: -0.03em;
      word-break: break-word;
    }}
    .window-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .window-chip {{
      background: white; border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px;
    }}
    .window-chip strong {{ display: block; margin-top: 6px; font-size: 20px; letter-spacing: -0.03em; }}
    .mini-grid {{ display: grid; gap: 10px; margin-top: 10px; }}
    .mini-row {{
      display: flex; justify-content: space-between; gap: 10px; padding: 10px 12px; border-radius: 12px;
      background: rgba(15, 92, 77, 0.06); border: 1px solid rgba(15, 92, 77, 0.08);
    }}
    .news-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .source-brief-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .source-brief {{
      border: 1px solid rgba(15, 92, 77, 0.1); border-radius: 16px; padding: 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(15, 92, 77, 0.03));
    }}
    .source-brief-top {{
      display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 10px;
    }}
    .source-brief-name {{ font-size: 16px; font-weight: 700; letter-spacing: -0.02em; }}
    .source-brief-id, .source-brief-count {{
      color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .source-brief-copy {{ margin: 8px 0 0; color: var(--muted); font-size: 14px; line-height: 1.6; }}
    .source-availability {{
      display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .source-dot {{ width: 10px; height: 10px; border-radius: 999px; display: inline-block; }}
    .dot-ok {{ background: #1f9f58; box-shadow: 0 0 0 4px rgba(31, 159, 88, 0.12); }}
    .dot-issue {{ background: #d66a1f; box-shadow: 0 0 0 4px rgba(214, 106, 31, 0.12); }}
    .dot-idle {{ background: #9aa39f; box-shadow: 0 0 0 4px rgba(154, 163, 159, 0.14); }}
    .news-toolbar {{
      display: flex; justify-content: space-between; align-items: center; gap: 12px;
      flex-wrap: wrap; margin-bottom: 14px;
    }}
    .news-control {{
      display: inline-flex; align-items: center; gap: 10px; color: var(--muted); font-size: 14px;
    }}
    .news-control select {{
      border: 1px solid var(--line); background: white; border-radius: 999px; padding: 8px 12px;
      font: inherit; color: var(--ink);
    }}
    .news-item {{
      text-decoration: none; color: inherit; display: block;
      background: linear-gradient(180deg, rgba(15, 92, 77, 0.06), rgba(15, 92, 77, 0.02));
      border: 1px solid rgba(15, 92, 77, 0.1); border-radius: 16px; padding: 16px;
    }}
    .news-item h3 {{ margin: 10px 0; font-size: 18px; line-height: 1.45; }}
    .news-reason {{ margin: 0 0 12px; color: var(--ink); font-size: 14px; line-height: 1.6; }}
    .news-head, .news-meta {{
      display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
      color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 960px) {{
      .summary-grid, .window-grid, .news-grid, .source-brief-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="eyebrow">Decision Dashboard</div>
    <h1>{escape(text['title'])}</h1>
    <p class="subtitle">{escape(text['subtitle'])}</p>
    <p class="compact-note">{escape(text['latest_forecast_time'])}: {escape(str(updated_at))}</p>

    <div class="dashboard">
      <section class="summary-grid">
        <div class="card">
          <div class="stat-label">{escape(text['end_time'])}</div>
          <div class="stat-value">{escape(str(window.get('p50', '-')))}</div>
          <div class="window-grid">
            <div class="window-chip">P10<strong>{escape(str(window.get('p10', '-')))}</strong></div>
            <div class="window-chip">P50<strong>{escape(str(window.get('p50', '-')))}</strong></div>
            <div class="window-chip">P90<strong>{escape(str(window.get('p90', '-')))}</strong></div>
          </div>
          <div class="mini-grid">{end_windows}</div>
        </div>
        <div class="card">
          <div class="stat-label">{escape(text['prediction'])}</div>
          <div class="stat-value">{escape(str(decision_panel.get('most_likely_outcome', '-')))}</div>
          <p class="compact-note">{escape(text['current_war_state'])}: {escape(str(decision_panel.get('current_state', '-')))}</p>
          <p class="compact-note">{escape(text['evidence_items'])}: {escape(str(latest_summary.get('item_count', 0)))}</p>
          <p class="compact-note">{escape(text['tension_index'])}: {escape(str(latest_summary.get('tension_index', '-')))}</p>
        </div>
        <div class="card">
          <div class="stat-label">{escape(text['confidence_value'])}</div>
          <div class="stat-value">{escape(str(confidence.get('score', '-')))}</div>
          <p class="compact-note">{escape(text['tier'])}: {escape(str(confidence.get('tier', '-')))}</p>
          <p class="compact-note">{escape(text['confidence'])}: {escape(str(latest_forecast.get('confidence_note', '-')))}</p>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">{escape(text['important_news'])}</h2>
        {news_section}
      </section>

      {source_brief_section}
    </div>
  </div>
</body>
</html>
"""


def make_handler(service: SandboxService):
    class Handler(BaseHTTPRequestHandler):
        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location: str = "/") -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def _read_form(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            return parse_qs(raw, keep_blank_values=True)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._send_json(service.dashboard_state())
                return
            if parsed.path == "/":
                self._send_html(_html_page(service.dashboard_state()))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            form = self._read_form()
            if self.path == "/source/update":
                source_id = form.get("source_id", [""])[0]
                enabled = form.get("enabled", ["0"])[0] == "1"
                interval_seconds = int(form.get("interval_seconds", ["900"])[0])
                service.update_source(source_id, enabled, interval_seconds)
                self._redirect("/")
                return
            if self.path == "/source/run":
                source_id = form.get("source_id", [""])[0]
                service.run_source_safe(source_id)
                self._redirect("/")
                return
            if self.path == "/settings/update":
                settings = {
                    "forecast_interval_seconds": max(
                        60, int(form.get("forecast_interval_seconds", ["1800"])[0])
                    ),
                    "dashboard_refresh_seconds": max(
                        5, int(form.get("dashboard_refresh_seconds", ["15"])[0])
                    ),
                    "evidence_hours": 168,
                    "forecast_limit": max(50, int(form.get("forecast_limit", ["200"])[0])),
                    "auto_forecast": form.get("auto_forecast", ["1"])[0] == "1",
                    "language": form.get("language", ["zh"])[0],
                }
                service.update_settings(settings)
                self._redirect("/")
                return
            if self.path == "/forecast/run":
                try:
                    service.run_forecast()
                except Exception:
                    pass
                self._redirect("/")
                return
            self.send_error(404)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return Handler


def serve_forever(service: SandboxService, port: int) -> None:
    stop_event = threading.Event()
    worker = threading.Thread(
        target=service.loop_forever,
        args=(stop_event,),
        kwargs={"sleep_seconds": 5},
        daemon=True,
    )
    worker.start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.server_close()
