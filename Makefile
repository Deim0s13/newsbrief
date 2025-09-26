# ---- Config ----
IMAGE ?= newsbrief-api:dev
PORT  ?= 8787

# ---- Local dev ----
venv:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --port $(PORT)

refresh:
	curl -s -X POST http://localhost:$(PORT)/refresh | jq .

items:
	curl -s "http://localhost:$(PORT)/items?limit=20" | jq .

# ---- Container (Docker or Podman) ----
docker-build:
	docker build -t $(IMAGE) .

docker-run:
	# Mount ./data so SQLite persists; map port
	docker run --rm -it \
		-p $(PORT):$(PORT) \
		-v $$PWD/data:/app/data \
		-e OLLAMA_BASE_URL=$${OLLAMA_BASE_URL:-http://host.docker.internal:11434} \
		--name newsbrief $(IMAGE)

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

# ---- Podman tips ----
podman-run:
	podman run --rm -it \
		-p $(PORT):$(PORT) \
		-v $$PWD/data:/app/data \
		-e OLLAMA_BASE_URL=$${OLLAMA_BASE_URL:-http://host.containers.internal:11434} \
		--name newsbrief $(IMAGE)