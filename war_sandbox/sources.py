import hashlib
import json
import csv
import io
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .agent_browser import AgentBrowserError, agent_browser_available, browser_eval_json, browser_get_text


USER_AGENT = "mesimulation-war-sandbox/1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def normalize_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    formats = [
        "%Y%m%dT%H%M%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return value


def filter_by_hours(items: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered = []
    for item in items:
        published = normalize_timestamp(item.get("published_at"))
        item["published_at"] = published
        timestamp = published or item["fetched_at"]
        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            filtered.append(item)
            continue
        if dt >= cutoff:
            filtered.append(item)
    return filtered


def http_get_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body[:240].replace("\n", " ")
        raise ValueError(f"Non-JSON response from {url}: {preview}") from exc


def http_get_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def stable_id(source: str, url: str, title: str) -> str:
    return hashlib.sha256(f"{source}|{url}|{title}".encode("utf-8")).hexdigest()


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text


def _extract(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.I | re.S)
    return unescape(match.group(1)).strip() if match else None


def _parse_liveuamap_timestamp(url: str) -> Optional[str]:
    match = re.search(r"/(\d{4})/(\d{1,2})-([a-z]+)-(\d{1,2})-", url)
    if not match:
        return None
    year = int(match.group(1))
    day = int(match.group(2))
    month_name = match.group(3).title()
    hour = int(match.group(4))
    try:
        dt = datetime.strptime(f"{year} {month_name} {day} {hour}", "%Y %B %d %H")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _middle_east_filter(lat: Any, lon: Any, bounds: Dict[str, float]) -> bool:
    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError):
        return False
    return (
        bounds["lat_min"] <= lat_value <= bounds["lat_max"]
        and bounds["lon_min"] <= lon_value <= bounds["lon_max"]
    )


def fetch_gdelt(query: str, max_records: int = 50, hours: int = 72) -> List[Dict[str, Any]]:
    encoded = quote_plus(query)
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={encoded}&mode=ArtList&maxrecords={max_records}&format=json"
        f"&sort=DateDesc&timespan={hours}h"
    )
    payload = http_get_json(url)
    articles = payload.get("articles", [])
    fetched_at = utc_now()
    items = []
    for article in articles:
        title = article.get("title", "")
        url_value = article.get("url", "")
        text_parts = [
            title,
            article.get("seendate", ""),
            article.get("sourcecountry", ""),
            article.get("domain", ""),
            article.get("socialimage", ""),
        ]
        items.append(
            {
                "id": stable_id("gdelt", url_value, title),
                "source": "gdelt",
                "fetched_at": fetched_at,
                "published_at": normalize_timestamp(article.get("seendate")),
                "title": title,
                "url": url_value,
                "content_text": " | ".join(part for part in text_parts if part),
                "payload": article,
            }
        )
    return items


def fetch_gdelt_timeline(query: str, hours: int = 72) -> List[Dict[str, Any]]:
    encoded = quote_plus(query)
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={encoded}&mode=TimelineVolRaw&format=json&timespan={hours}h"
    )
    payload = http_get_json(url)
    series = payload.get("timeline", [])
    if not series:
        return []
    data = series[0].get("data", [])
    if not data:
        return []
    latest = data[-1]
    peak = max(data, key=lambda row: row.get("value", 0))
    norm_peak = max(data, key=lambda row: row.get("norm", 0))
    fetched_at = utc_now()
    latest_ts = normalize_timestamp(latest.get("date"))
    latest_value = int(latest.get("value", 0))
    latest_norm = int(latest.get("norm", 0))
    peak_text = (
        f"latest={latest_value}, latest_norm={latest_norm}, "
        f"peak_count={peak.get('value', 0)} at {peak.get('date')}, "
        f"peak_norm={norm_peak.get('norm', 0)} at {norm_peak.get('date')}"
    )
    return [
        {
            "id": stable_id("gdelt_timeline", url, "gdelt_timeline"),
            "source": "gdelt_timeline",
            "fetched_at": fetched_at,
            "published_at": latest_ts,
            "title": "GDELT event intensity pulse",
            "url": url,
            "content_text": peak_text,
            "payload": {
                "query_details": payload.get("query_details", {}),
                "latest": latest,
                "peak": peak,
                "norm_peak": norm_peak,
            },
        }
    ]


def fetch_reliefweb(query: str, limit: int = 20, appname: str = "mesimulation") -> List[Dict[str, Any]]:
    encoded = quote_plus(query)
    url = (
        "https://api.reliefweb.int/v1/reports"
        f"?appname={quote_plus(appname)}&query[value]={encoded}&limit={limit}"
        "&profile=full&sort[]=date:desc"
    )
    payload = http_get_json(url)
    data = payload.get("data", [])
    fetched_at = utc_now()
    items = []
    for entry in data:
        fields = entry.get("fields", {})
        title = fields.get("title", "")
        url_value = fields.get("url") or fields.get("origin") or ""
        body = fields.get("body-html") or fields.get("body") or ""
        items.append(
            {
                "id": stable_id("reliefweb", url_value, title),
                "source": "reliefweb",
                "fetched_at": fetched_at,
                "published_at": normalize_timestamp(fields.get("date", {}).get("created")),
                "title": title,
                "url": url_value,
                "content_text": body[:5000],
                "payload": entry,
            }
        )
    return items


def fetch_liveuamap_iran(max_records: int = 20) -> List[Dict[str, Any]]:
    page_url = "https://iran.liveuamap.com/en"
    try:
        body = http_get_text(page_url)
    except Exception:
        body = ""
    if "Attention Required!" in body and agent_browser_available():
        body = browser_get_text(page_url, max_output=4000)
    if "Attention Required!" in body:
        raise ValueError("LiveUAmap blocked this IP even in a real browser session")
    links = []
    seen = set()
    for link in re.findall(r"https://iran\.liveuamap\.com/en/\d{4}/[^\"'<> ]+", body):
        if link in seen:
            continue
        seen.add(link)
        links.append(link)
    fetched_at = utc_now()
    items = []
    for link in links[:max_records]:
        article = http_get_text(link)
        title = _extract(r'<meta property="og:title" content="([^"]+)"', article) or link.rsplit("/", 1)[-1]
        description = _extract(r'<meta property="og:description" content="([^"]+)"', article) or ""
        published_at = (
            normalize_timestamp(_extract(r'<meta property="article:published_time" content="([^"]+)"', article))
            or _parse_liveuamap_timestamp(link)
        )
        items.append(
            {
                "id": stable_id("liveuamap_iran", link, title),
                "source": "liveuamap_iran",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": title,
                "url": link,
                "content_text": _strip_html(description)[:4000],
                "payload": {
                    "title": title,
                    "description": description,
                    "link": link,
                },
            }
        )
    return items


def fetch_iaea_news(max_records: int = 12) -> List[Dict[str, Any]]:
    url = "https://www.iaea.org/newscenter/news"
    body = http_get_text(url)
    fetched_at = utc_now()
    items = []
    for match in re.finditer(r'<div class="card w-100 mb-4">(.+?)</div>\s*</div>\s*</div>', body, re.I | re.S):
        block = match.group(1)
        link = _extract(r'<h3 class="card__title">\s*<a href="([^"]+)"', block)
        title = _extract(r'<h3 class="card__title">\s*<a [^>]+>(.*?)</a>', block)
        date_text = _extract(r'<p class="card__date[^"]*">([^<]+)</p>', block)
        if not link or not title:
            continue
        published_at = None
        if date_text:
            try:
                published_at = datetime.strptime(date_text.strip(), "%d %B %Y").replace(
                    tzinfo=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                published_at = normalize_timestamp(date_text)
        full_url = urljoin("https://www.iaea.org", link)
        items.append(
            {
                "id": stable_id("iaea_news", full_url, title),
                "source": "iaea_news",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": _strip_html(title),
                "url": full_url,
                "content_text": _strip_html(title),
                "payload": {
                    "link": full_url,
                    "date_text": date_text,
                },
            }
        )
        if len(items) >= max_records:
            break
    return items


def fetch_centcom_dvids(max_records: int = 12) -> List[Dict[str, Any]]:
    url = "https://www.dvidshub.net/cocom/USCENTCOM"
    body = http_get_text(url)
    fetched_at = utc_now()
    items = []
    for match in re.finditer(r"<article class=\"uk-comment.*?</article>", body, re.I | re.S):
        block = match.group(0)
        link = _extract(r'href="(/news/\d+/[^"]+)"', block)
        title = _extract(r'title="([^"]+)" class="assetTitle"', block) or _extract(
            r'title="([^"]+)" class="assetLink"',
            block,
        )
        if not link or not title:
            continue
        date_text = _extract(r'uk-comment-meta">([^<|]+)', block) or ""
        snippet = _extract(r'<div class="uk-comment-body">(.+?)</div>', block) or ""
        published_at = None
        if date_text:
            try:
                published_at = datetime.strptime(date_text.strip(), "%m.%d.%Y").replace(
                    tzinfo=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                published_at = normalize_timestamp(date_text)
        full_url = urljoin("https://www.dvidshub.net", link)
        items.append(
            {
                "id": stable_id("centcom_dvids", full_url, title),
                "source": "centcom_dvids",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": title,
                "url": full_url,
                "content_text": _strip_html(snippet)[:4000],
                "payload": {
                    "date_text": date_text,
                    "snippet": snippet,
                    "link": full_url,
                },
            }
        )
        if len(items) >= max_records:
            break
    return items


def fetch_adsb_military(bounds: Dict[str, float], limit: int = 40) -> List[Dict[str, Any]]:
    payload = http_get_json("https://api.adsb.lol/v2/mil")
    aircraft = payload.get("ac", [])
    fetched_at = utc_now()
    items = []
    for row in aircraft:
        if not _middle_east_filter(row.get("lat"), row.get("lon"), bounds):
            continue
        flight = (row.get("flight") or "").strip() or (row.get("r") or "").strip() or row.get("hex", "unknown")
        aircraft_type = (row.get("t") or "unknown").strip()
        title = f"Military flight {flight} ({aircraft_type}) detected over Middle East"
        content = (
            f"lat={row.get('lat')}, lon={row.get('lon')}, alt={row.get('alt_baro')}, "
            f"gs={row.get('gs')}, track={row.get('track')}, hex={row.get('hex')}, "
            f"registration={row.get('r')}, dbFlags={row.get('dbFlags')}"
        )
        items.append(
            {
                "id": stable_id("adsb_military", row.get("hex", ""), f"{flight}|{row.get('lat')}|{row.get('lon')}"),
                "source": "adsb_military",
                "fetched_at": fetched_at,
                "published_at": fetched_at,
                "title": title,
                "url": f"https://globe.adsb.lol/?icao={row.get('hex', '')}",
                "content_text": content,
                "payload": row,
            }
        )
    items.sort(key=lambda item: item["title"])
    return items[:limit]


def fetch_firms_hotspots(map_key: str, west: float, south: float, east: float, north: float, day_range: int = 1, limit: int = 50) -> List[Dict[str, Any]]:
    area = f"{west},{south},{east},{north}"
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{quote_plus(map_key)}/VIIRS_SNPP_NRT/{area}/{int(day_range)}"
    )
    csv_text = http_get_bytes(url).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_text))
    fetched_at = utc_now()
    items = []
    for row in reader:
        title = f"NASA FIRMS hotspot near {row.get('latitude')}, {row.get('longitude')}"
        acq_time = str(row.get("acq_time") or "").zfill(4)
        date_text = " ".join(
            filter(
                None,
                [
                    row.get("acq_date"),
                    f"{acq_time[:2]}:{acq_time[2:]}:00" if acq_time.strip("0") else None,
                ],
            )
        )
        items.append(
            {
                "id": stable_id("nasa_firms", f"{row.get('latitude')}|{row.get('longitude')}", date_text),
                "source": "nasa_firms",
                "fetched_at": fetched_at,
                "published_at": normalize_timestamp(date_text),
                "title": title,
                "url": "https://firms.modaps.eosdis.nasa.gov/",
                "content_text": json.dumps(row, ensure_ascii=False),
                "payload": row,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_irna_english() -> List[Dict[str, Any]]:
    if not agent_browser_available():
        raise ValueError("IRNA English requires Vercel agent-browser")
    script = """
JSON.stringify({
  title: document.title || "",
  text: (document.body && document.body.innerText ? document.body.innerText : "").slice(0, 1200),
  url: location.href
})
""".strip()
    payload = browser_eval_json("https://en.irna.ir/", script, wait_ms=3500, retries=5, retry_delay_seconds=1.5)
    text = str((payload or {}).get("text", "")).strip()
    title = str((payload or {}).get("title", "")).strip()
    if "Gateway Timeout" in text or "Transferring to the website" in text or "Error 504" in title:
        raise ValueError("IRNA English returned a gateway/challenge page after browser rendering")
    raise ValueError("IRNA English browser rendering did not yield a stable article listing")


def fetch_tasnim_english() -> List[Dict[str, Any]]:
    raise ValueError("Tasnim English DNS is not resolvable from this runtime")


def fetch_idf_releases(max_records: int = 12) -> List[Dict[str, Any]]:
    if not agent_browser_available():
        raise ValueError("IDF media releases require Vercel agent-browser")
    script = r"""
JSON.stringify(
  Array.from(document.querySelectorAll('a[href*="/mini-sites/idf-press-releases-israel-at-war/"]'))
    .map((anchor) => ({
      href: anchor.href,
      text: (anchor.textContent || "").replace(/\s+/g, " ").trim()
    }))
    .filter((item) =>
      item.href &&
      item.href.includes('/mini-sites/idf-press-releases-israel-at-war/') &&
      !item.href.endsWith('/mini-sites/idf-press-releases-israel-at-war/') &&
      item.text.length > 12
    )
)
""".strip()
    payload = browser_eval_json(
        "https://www.idf.il/en/mini-sites/press-releases/",
        script,
        wait_ms=1200,
        retries=3,
        retry_delay_seconds=1.0,
    )
    if not isinstance(payload, list):
        raise ValueError("IDF browser extraction did not return a list")
    fetched_at = utc_now()
    items = []
    seen = set()
    for row in payload:
        href = str(row.get("href", "")).strip()
        text = _strip_html(str(row.get("text", "")))
        if not href or href in seen:
            continue
        seen.add(href)
        match = re.match(r"([A-Za-z]+ \d{1,2}, \d{4})\s+(.*)", text)
        published_at = None
        title = text
        if match:
            published_at = normalize_timestamp(match.group(1))
            title = match.group(2).strip()
        if len(title) < 12:
            continue
        items.append(
            {
                "id": stable_id("idf_releases", href, title),
                "source": "idf_releases",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": title,
                "url": href,
                "content_text": text[:4000],
                "payload": row,
            }
        )
        if len(items) >= max_records:
            break
    return items


def fetch_presstv_latest(max_records: int = 12) -> List[Dict[str, Any]]:
    url = "https://www.presstv.ir/"
    body = http_get_text(url)
    fetched_at = utc_now()
    items = []
    seen = set()
    pattern = re.compile(
        r'<a[^>]+href=(["\']?)(/Detail/\d{4}/\d{2}/\d{2}/\d+/[^"\'>\s]+)\1[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for match in pattern.finditer(body):
        link = urljoin(url, match.group(2))
        if link in seen:
            continue
        seen.add(link)
        text = _strip_html(match.group(3))
        if len(text) < 18:
            continue
        date_match = re.search(r"/Detail/(\d{4})/(\d{2})/(\d{2})/", link)
        published_at = None
        if date_match:
            published_at = normalize_timestamp(
                f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)} 00:00:00"
            )
        items.append(
            {
                "id": stable_id("presstv_latest", link, text),
                "source": "presstv_latest",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": text,
                "url": link,
                "content_text": text[:4000],
                "payload": {
                    "link": link,
                    "title": text,
                },
            }
        )
        if len(items) >= max_records:
            break
    return items


def fetch_acled() -> List[Dict[str, Any]]:
    raise ValueError("ACLED requires account credentials and is configured as calibration-only")


def fetch_vesselfinder() -> List[Dict[str, Any]]:
    raise ValueError("VesselFinder realtime API is not available as a free public feed")


def fetch_rss(feed_name: str, url: str) -> List[Dict[str, Any]]:
    xml_text = http_get_text(url)
    root = ET.fromstring(xml_text)
    fetched_at = utc_now()
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        description = item.findtext("description", default="")
        pub_date = item.findtext("pubDate")
        published_at = normalize_timestamp(pub_date)
        items.append(
            {
                "id": stable_id(f"rss:{feed_name}", link, title),
                "source": f"rss:{feed_name}",
                "fetched_at": fetched_at,
                "published_at": published_at,
                "title": title,
                "url": link,
                "content_text": description[:4000],
                "payload": {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pubDate": pub_date,
                },
            }
        )
    return items


def load_rss_config(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
