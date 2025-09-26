APP_PORT ?= 8787
IMAGE ?= newsbrief

.PHONY: setup venv lock run-local build run stop logs refresh

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

venv:
	. .venv/bin/activate

run-local:
	. .venv/bin/activate; uvicorn app.main:app --reload --port $(APP_PORT)

build:
	podman build -t $(IMAGE) .

run:
	podman run --name $(IMAGE) -p 127.0.0.1:$(APP_PORT):8787 \
	  -v $(PWD)/data:/app/data \
	  -e SUMMARY_MODEL=llama3.1:8b \
	  -e OLLAMA_HOST=http://host.containers.internal:11434 \
	  $(IMAGE)

stop:
	podman stop $(IMAGE) || true && podman rm $(IMAGE) || true

logs:
	podman logs -f $(IMAGE)

refresh:
	curl -X POST http://localhost:$(APP_PORT)/refresh