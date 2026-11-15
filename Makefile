# Prototype deps are pinned in prototype/api/requirements.txt; uv builds a cached env on first use.
UV=uv run --no-project --python 3.12 --with-requirements $(CURDIR)/prototype/api/requirements.txt
PY=$(UV) python
# ngrok static domain (O-08): put the domain in prototype/api/NGROK_DOMAIN (git-ignored).
NGROK_DOMAIN=$(shell cat prototype/api/NGROK_DOMAIN 2>/dev/null)

api:
	cd prototype/api && $(UV) uvicorn app:app --port 8799 --reload

tunnel:
	@test -n "$(NGROK_DOMAIN)" || { echo "missing prototype/api/NGROK_DOMAIN (see docs/dev-loop.md)"; exit 1; }
	ngrok http --url=$(NGROK_DOMAIN) 8799

tunnel-serveo:
	ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8799 serveo.net

check:
	cd prototype/api && $(PY) app.py > /dev/null && echo "schema self-check ok"
	$(PY) prototype/replay_fixtures.py
