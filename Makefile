PYTHON ?= python3

.PHONY: init ingest forecast report list score serve export-pages publish-pages publish-loop

init:
	$(PYTHON) -m war_sandbox.cli init-db

ingest:
	$(PYTHON) -m war_sandbox.cli ingest --hours 72

forecast:
	$(PYTHON) -m war_sandbox.cli forecast --hours 72

report:
	$(PYTHON) -m war_sandbox.cli report --latest

list:
	$(PYTHON) -m war_sandbox.cli list-forecasts

score:
	$(PYTHON) -m war_sandbox.cli score

serve:
	$(PYTHON) -m war_sandbox.cli serve --port 8080

export-pages:
	$(PYTHON) -m war_sandbox.cli export-pages --output-dir docs

publish-pages:
	$(PYTHON) -m war_sandbox.cli publish-pages --repo-root . --output-dir docs

publish-loop:
	$(PYTHON) -m war_sandbox.cli publish-loop --repo-root . --output-dir docs --sleep-seconds 300
