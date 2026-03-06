# Iran War Sandbox

This repository contains a command-line forecasting system for near-real-time
scenario analysis of the Iran war theater using only:

- free/open data services
- local orchestration with Python standard library
- `gemini` CLI for inference

It is designed for probabilistic scenario planning, not deterministic prophecy.
Outputs about war termination, political succession, or post-war policy are
explicitly marked as scenarios with evidence, assumptions, and uncertainty.

## What it does

- Ingests free/open sources from GDELT, ReliefWeb, and optional RSS feeds
- Stores raw items in SQLite
- Builds a structured brief for the latest evidence window
- Calls `gemini --prompt` in headless mode and forces JSON output
- Produces:
  - war end time window (`p10`, `p50`, `p90`)
  - outcome probabilities
  - successor government scenarios
  - likely institutional architecture
  - first-180-day policy assumptions
  - watch indicators and confidence drivers
- Saves every forecast for audit and backtesting

## Constraints

- No paid LLM API
- No proprietary forecasting service
- No GUI requirement
- No third-party Python dependencies

## Quick start

```bash
python3 -m war_sandbox.cli init-db
python3 -m war_sandbox.cli ingest \
  --query '(Iran OR IRGC OR Israel OR ceasefire)' \
  --hours 72
python3 -m war_sandbox.cli forecast --hours 72
python3 -m war_sandbox.cli report --latest
```

## Local web dashboard

Run the continuously looping local service:

```bash
python3 -m war_sandbox.cli serve --port 8080
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

The page shows:

- all configured data sources
- last run status for each source
- per-source update interval controls
- manual "run now" actions
- forecast interval controls
- latest forecast summary and report
- Chinese and English UI switching from the top menu, defaulting to Chinese

## GitHub Pages snapshot

GitHub Pages cannot run the local Python service. This project therefore exports
a static snapshot page with only:

- end window
- outcome call
- confidence
- filtered important news

Generate the static page into `docs/`:

```bash
python3 -m war_sandbox.cli export-pages --output-dir docs
```

That writes:

- `docs/index.html`
- `docs/.nojekyll`

You can publish that folder with GitHub Pages from the repository branch you
push to.

## Local Agent -> GitHub Pages

If you want the local agent to keep GitHub Pages updated, use the publishing
commands instead of manually exporting and pushing:

```bash
python3 -m war_sandbox.cli publish-pages --repo-root . --output-dir docs
python3 -m war_sandbox.cli publish-loop --repo-root . --output-dir docs --sleep-seconds 300
```

Behavior:

- `publish-pages`
  - runs a normal pipeline tick
  - exports the latest static snapshot into `docs/`
  - commits only if `docs/` changed
  - pushes to `origin main`
- `publish-loop`
  - keeps running locally
  - periodically repeats the same export + commit + push cycle
  - this is the mode to use if your local machine is the publishing agent

## Optional RSS configuration

Edit [examples/rss_sources.json](/Users/occ/work/mesimulation/examples/rss_sources.json)
and then run:

```bash
python3 -m war_sandbox.cli ingest --rss /Users/occ/work/mesimulation/examples/rss_sources.json
```

If you have an approved ReliefWeb app name:

```bash
export RELIEFWEB_APPNAME='your-approved-appname'
python3 -m war_sandbox.cli ingest --reliefweb-appname "$RELIEFWEB_APPNAME"
```

## System architecture

1. Source adapters
- `GDELT DOC 2.0` article search
- `ReliefWeb` reports API
- generic RSS adapter
2. Evidence store
   - raw items in SQLite
   - every forecast stored as immutable snapshot
3. Feature layer
   - actor mentions
   - escalation/de-escalation phrases
   - leadership continuity markers
   - regime cohesion and opposition visibility markers
4. Scenario engine
   - deterministic summary + `gemini` structured forecast
   - probability normalization and schema checks
5. Reporting
   - JSON archive
   - Markdown decision brief
6. Evaluation
   - simple Brier score for resolved binary or categorical questions

## Why this is structured this way

Forecasting war termination and succession is fragile. A free-CLI-only system is
most useful when it separates:

- evidence collection
- structured state summarization
- scenario generation
- probability tracking
- later scoring

That prevents the model from acting like an untracked narrative generator.

## Important warning

Predictions about successor governments and named figures are scenario-ranked
hypotheses derived from open-source evidence. They are not facts, not guidance,
and not a substitute for intelligence-grade validation.

## Main commands

```bash
python3 -m war_sandbox.cli init-db
python3 -m war_sandbox.cli ingest [--query ...] [--hours 72] [--rss path.json]
python3 -m war_sandbox.cli forecast [--hours 72] [--model gemini-3-flash-preview]
python3 -m war_sandbox.cli report --latest
python3 -m war_sandbox.cli list-forecasts
python3 -m war_sandbox.cli score --forecast-id <id> --resolved-outcome negotiated_ceasefire
python3 -m war_sandbox.cli serve --port 8080
python3 -m war_sandbox.cli publish-pages --repo-root . --output-dir docs
python3 -m war_sandbox.cli publish-loop --repo-root . --output-dir docs --sleep-seconds 300
```

## Background services

- `launchd/com.occ.mesandbox.publish-loop.plist`: login-time auto-publish to GitHub Pages
- `launchd/com.occ.mesandbox.serve-8080.plist`: login-time local dashboard on `http://127.0.0.1:8080`
- `scripts/publish_loop.sh`: wrapper for the publish loop
- `scripts/serve_8080.sh`: wrapper for the local web server

## GitHub Pages mode

Use GitHub Pages in `Deploy from a branch` mode:

- Branch: `main`
- Folder: `/docs`

The local `publish-loop` updates `docs/index.html` and pushes commits directly.
`docs/.nojekyll` is included so Pages serves the static snapshot without a Jekyll build.

## Files

- [war_sandbox/cli.py](/Users/occ/work/mesimulation/war_sandbox/cli.py)
- [war_sandbox/sources.py](/Users/occ/work/mesimulation/war_sandbox/sources.py)
- [war_sandbox/gemini_runner.py](/Users/occ/work/mesimulation/war_sandbox/gemini_runner.py)
- [war_sandbox/scenario.py](/Users/occ/work/mesimulation/war_sandbox/scenario.py)
- [war_sandbox/db.py](/Users/occ/work/mesimulation/war_sandbox/db.py)
- [schemas/forecast.schema.json](/Users/occ/work/mesimulation/schemas/forecast.schema.json)

## Reference services

- [GDELT](https://www.gdeltproject.org/)
- [ReliefWeb API](https://reliefweb.int/help/api)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli)

## Operational note

`GDELT` sometimes rate-limits aggressively. The ingest command is built to keep
running if one source fails, so RSS and any other enabled source can still
sustain the pipeline.

`ReliefWeb` stays disabled until `RELIEFWEB_APPNAME` is set to an approved app
name, to avoid a permanent error state in the dashboard.
