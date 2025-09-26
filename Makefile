APP_PORT ?= 8787
IMAGE ?= newsbrief

.PHONY: setup venv lock run-local build run stop logs refresh

setup:
\tpython3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

venv:
\t. .venv/bin/activate

run-local:
\t. .venv/bin/activate; uvicorn app.main:app --reload --port $(APP_PORT)

build:
\tpodman build -t $(IMAGE) .

run:
\tpodman run --name $(IMAGE) -p 127.0.0.1:$(APP_PORT):8787 \
\t  -v $(PWD)/data:/app/data \
\t  -e SUMMARY_MODEL=llama3.1:8b \
\t  -e OLLAMA_HOST=http://host.containers.internal:11434 \
\t  $(IMAGE)

stop:
\tpodman stop $(IMAGE) || true && podman rm $(IMAGE) || true

logs:
\tpodman logs -f $(IMAGE)

refresh:
\tcurl -X POST http://localhost:$(APP_PORT)/refresh