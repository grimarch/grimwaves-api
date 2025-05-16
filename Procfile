web: poetry run uvicorn grimwaves_api:app --host 0.0.0.0 --port $(jq -r .server.port data/config.json) --workers $(jq -r .server.workers data/config.json)
