import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    DEFAULT_FORECAST_LIMIT,
    DEFAULT_HOURS,
    DEFAULT_PORT,
    DEFAULT_QUERY,
    RELIEFWEB_APPNAME,
    REPORT_DIR,
    RSS_CONFIG_PATH,
)
from .db import (
    fetch_recent_items,
    fetch_latest_items_by_sources,
    get_forecast,
    get_runtime_setting,
    insert_forecast,
    insert_raw_items,
    list_forecasts,
)
from .report import categorical_brier, render_markdown
from .publisher import build_service, publish_loop, publish_once
from .scenario import generate_forecast
from .service import SandboxService, bootstrap_state
from .webapp import render_static_snapshot
from .sources import (
    fetch_gdelt,
    fetch_reliefweb,
    fetch_rss,
    filter_by_hours,
    load_rss_config,
)
from .war_state import build_analysis_package


CRITICAL_SNAPSHOT_SOURCES = ("oil_market", "polymarket_geopolitics", "gdelt_timeline")


def _merge_unique_items(primary, extra):
    merged = {str(item.get("id")): item for item in primary if item.get("id")}
    ordered = [item for item in primary if item.get("id")]
    for item in extra:
        item_id = str(item.get("id"))
        if not item_id or item_id in merged:
            continue
        merged[item_id] = item
        ordered.append(item)
    return ordered


def cmd_init_db(_: argparse.Namespace) -> None:
    bootstrap_state()
    print("initialized", flush=True)


def cmd_ingest(args: argparse.Namespace) -> None:
    items = []
    errors = []
    try:
        items.extend(fetch_gdelt(args.query, max_records=args.gdelt_max, hours=args.hours))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"gdelt: {exc}")
    try:
        if args.reliefweb_appname:
            items.extend(
                fetch_reliefweb(
                    args.query,
                    limit=args.reliefweb_max,
                    appname=args.reliefweb_appname,
                )
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"reliefweb: {exc}")
    if args.rss:
        for feed in load_rss_config(args.rss):
            try:
                items.extend(fetch_rss(feed["name"], feed["url"]))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"rss:{feed['name']}: {exc}")
    items = filter_by_hours(items, args.hours)
    count = insert_raw_items(items)
    print(json.dumps({"inserted": count, "errors": errors}, ensure_ascii=False))


def cmd_forecast(args: argparse.Namespace) -> None:
    items = fetch_recent_items(args.hours, limit=args.limit)
    items = _merge_unique_items(items, fetch_latest_items_by_sources(CRITICAL_SNAPSHOT_SOURCES))
    if not items:
        raise SystemExit("No evidence items found. Run ingest first.")

    language = get_runtime_setting("language", "zh")
    summary = build_analysis_package(items, language=language, model=args.model)
    forecast = generate_forecast(summary, model=args.model, language=language)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report_markdown = render_markdown(summary, forecast, language=language)
    forecast_id = forecast["forecast_id"]
    insert_forecast(
        forecast_id=forecast_id,
        created_at=created_at,
        evidence_hours=args.hours,
        model=args.model or "default",
        summary=summary,
        forecast=forecast,
        report_markdown=report_markdown,
    )
    report_path = REPORT_DIR / f"{forecast_id}.md"
    report_path.write_text(report_markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "forecast_id": forecast_id,
                "report_path": str(report_path),
                "items_used": len(items),
            },
            ensure_ascii=False,
        )
    )


def cmd_report(args: argparse.Namespace) -> None:
    row = get_forecast(None if args.latest else args.forecast_id)
    if not row:
        raise SystemExit("No forecast found.")
    print(row["report_markdown"])


def cmd_list_forecasts(_: argparse.Namespace) -> None:
    rows = list_forecasts()
    for row in rows:
        print(
            json.dumps(
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "evidence_hours": row["evidence_hours"],
                    "model": row["model"],
                },
                ensure_ascii=False,
            )
        )


def cmd_score(args: argparse.Namespace) -> None:
    row = get_forecast(args.forecast_id)
    if not row:
        raise SystemExit("Forecast not found.")
    forecast = json.loads(row["forecast_json"])
    score = categorical_brier(
        forecast.get("outcome_probabilities", []),
        args.resolved_outcome,
    )
    print(
        json.dumps(
            {
                "forecast_id": row["id"],
                "resolved_outcome": args.resolved_outcome,
                "brier": score,
            },
            ensure_ascii=False,
        )
    )


def cmd_serve(args: argparse.Namespace) -> None:
    bootstrap_state(rss_path=args.rss or str(args.default_rss_path))
    service = SandboxService(
        rss_path=args.rss or str(args.default_rss_path),
        model=args.model,
    )
    from .webapp import serve_forever

    print(
        json.dumps(
            {
                "status": "serving",
                "url": f"http://127.0.0.1:{args.port}",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    serve_forever(service, port=args.port)


def cmd_export_pages(args: argparse.Namespace) -> None:
    bootstrap_state(rss_path=args.rss or str(args.default_rss_path))
    service = SandboxService(
        rss_path=args.rss or str(args.default_rss_path),
        model=args.model,
    )
    state = service.dashboard_state()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "index.html"
    html_path.write_text(render_static_snapshot(state), encoding="utf-8")
    nojekyll = output_dir / ".nojekyll"
    nojekyll.write_text("", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(html_path),
            },
            ensure_ascii=False,
        )
    )


def cmd_publish_pages(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    service = build_service(
        rss_path=args.rss or str(args.default_rss_path),
        model=args.model,
    )
    result = publish_once(
        service=service,
        repo_root=repo_root,
        output_dir=(repo_root / args.output_dir).resolve(),
        remote=args.remote,
        branch=args.branch,
        commit_message_prefix=args.commit_prefix,
        tick=not args.no_tick,
    )
    print(json.dumps(result, ensure_ascii=False))


def cmd_publish_loop(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    service = build_service(
        rss_path=args.rss or str(args.default_rss_path),
        model=args.model,
    )
    publish_loop(
        service=service,
        repo_root=repo_root,
        output_dir=(repo_root / args.output_dir).resolve(),
        remote=args.remote,
        branch=args.branch,
        commit_message_prefix=args.commit_prefix,
        sleep_seconds=args.sleep_seconds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Iran war sandbox")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db")
    init_parser.set_defaults(func=cmd_init_db)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--query", default=DEFAULT_QUERY)
    ingest_parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    ingest_parser.add_argument("--gdelt-max", type=int, default=50)
    ingest_parser.add_argument("--reliefweb-max", type=int, default=20)
    ingest_parser.add_argument("--reliefweb-appname", default=RELIEFWEB_APPNAME)
    ingest_parser.add_argument("--rss")
    ingest_parser.set_defaults(func=cmd_ingest)

    forecast_parser = subparsers.add_parser("forecast")
    forecast_parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    forecast_parser.add_argument("--limit", type=int, default=DEFAULT_FORECAST_LIMIT)
    forecast_parser.add_argument("--model")
    forecast_parser.set_defaults(func=cmd_forecast)

    report_parser = subparsers.add_parser("report")
    report_group = report_parser.add_mutually_exclusive_group(required=True)
    report_group.add_argument("--latest", action="store_true")
    report_group.add_argument("--forecast-id")
    report_parser.set_defaults(func=cmd_report)

    list_parser = subparsers.add_parser("list-forecasts")
    list_parser.set_defaults(func=cmd_list_forecasts)

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--forecast-id", required=True)
    score_parser.add_argument("--resolved-outcome", required=True)
    score_parser.set_defaults(func=cmd_score)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--rss")
    serve_parser.add_argument("--model")
    serve_parser.add_argument("--default-rss-path", default=str(RSS_CONFIG_PATH))
    serve_parser.set_defaults(func=cmd_serve)

    export_parser = subparsers.add_parser("export-pages")
    export_parser.add_argument("--output-dir", default="docs")
    export_parser.add_argument("--rss")
    export_parser.add_argument("--model")
    export_parser.add_argument("--default-rss-path", default=str(RSS_CONFIG_PATH))
    export_parser.set_defaults(func=cmd_export_pages)

    publish_parser = subparsers.add_parser("publish-pages")
    publish_parser.add_argument("--repo-root", default=".")
    publish_parser.add_argument("--output-dir", default="docs")
    publish_parser.add_argument("--remote", default="origin")
    publish_parser.add_argument("--branch", default="main")
    publish_parser.add_argument("--commit-prefix", default="Update Pages snapshot")
    publish_parser.add_argument("--rss")
    publish_parser.add_argument("--model")
    publish_parser.add_argument("--default-rss-path", default=str(RSS_CONFIG_PATH))
    publish_parser.add_argument("--no-tick", action="store_true")
    publish_parser.set_defaults(func=cmd_publish_pages)

    publish_loop_parser = subparsers.add_parser("publish-loop")
    publish_loop_parser.add_argument("--repo-root", default=".")
    publish_loop_parser.add_argument("--output-dir", default="docs")
    publish_loop_parser.add_argument("--remote", default="origin")
    publish_loop_parser.add_argument("--branch", default="main")
    publish_loop_parser.add_argument("--commit-prefix", default="Update Pages snapshot")
    publish_loop_parser.add_argument("--sleep-seconds", type=int, default=300)
    publish_loop_parser.add_argument("--rss")
    publish_loop_parser.add_argument("--model")
    publish_loop_parser.add_argument("--default-rss-path", default=str(RSS_CONFIG_PATH))
    publish_loop_parser.set_defaults(func=cmd_publish_loop)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
