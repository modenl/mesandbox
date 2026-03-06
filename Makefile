PYTHON ?= python3

.PHONY: init ingest forecast report list score serve

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
