PY=prototype/api/.venv/bin/python

api:
	cd prototype/api && .venv/bin/uvicorn app:app --port 8799 --reload

tunnel:
	ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8799 serveo.net

check:
	cd prototype/api && ../../$(PY) app.py > /dev/null && echo "schema self-check ok"
	$(PY) prototype/replay_fixtures.py
