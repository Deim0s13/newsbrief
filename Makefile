# ---------- Config ----------
RUNTIME          ?= podman
REGISTRY         ?=                         # e.g. ghcr.io/Deim0s13
IMAGE_NAME       ?= newsbrief-api
PORT             ?= 8787
DATA_DIR         ?= $(PWD)/data

# Version metadata
GIT_SHA          := $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
GIT_TAG          := $(shell git describe --tags --abbrev=0 2>/dev/null || true)
DATE_UTC         := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
# Override VERSION from env for releases; otherwise fall back to tag or "0.0.0"
VERSION          ?= $(if $(GIT_TAG),$(GIT_TAG),0.0.0)

# Image refs
IMAGE_LOCAL      := $(IMAGE_NAME):buildcache
# Fully qualified (for push) if REGISTRY is set, else local only
IMAGE_BASE       := $(if $(REGISTRY),$(REGISTRY)/$(IMAGE_NAME),$(IMAGE_NAME))

# Tags to apply to the built image
TAGS             ?= $(VERSION) $(GIT_SHA) $(shell date -u +%Y%m%d) latest

# ---------- Dev (host) ----------
venv:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run-local:
	uvicorn app.main:app --reload --port $(PORT)

# ---------- Build / Tag / Push ----------
build:
	$(RUNTIME) build \
		-t $(IMAGE_LOCAL) \
		--label org.opencontainers.image.title="$(IMAGE_NAME)" \
		--label org.opencontainers.image.version="$(VERSION)" \
		--label org.opencontainers.image.created="$(DATE_UTC)" \
		--label org.opencontainers.image.revision="$(GIT_SHA)" \
		--label org.opencontainers.image.source="$$(git config --get remote.origin.url 2>/dev/null || echo unknown)" \
		.

# Apply all tags to the built image (no rebuild)
tag: build
	@for t in $(TAGS); do \
		echo "Tagging: $(IMAGE_BASE):$$t"; \
		$(RUNTIME) tag $(IMAGE_LOCAL) $(IMAGE_BASE):$$t; \
	done

# Push every tag (only meaningful if REGISTRY is set)
push: tag
	@if [ -z "$(REGISTRY)" ]; then echo "REGISTRY is empty; skipping push." && exit 0; fi
	@for t in $(TAGS); do \
		echo "Pushing: $(IMAGE_BASE):$$t"; \
		$(RUNTIME) push $(IMAGE_BASE):$$t; \
	done

# Convenience targets
release:                          ## Example: make release VERSION=v0.2.0 REGISTRY=ghcr.io/deim0s13
	@test -n "$(VERSION)" || (echo "Set VERSION=vX.Y.Z" && exit 1)
	$(MAKE) push

local-release:                    ## Build and tag locally: make local-release VERSION=v0.2.0
	@test -n "$(VERSION)" || (echo "Set VERSION=vX.Y.Z" && exit 1)
	$(MAKE) tag

run:
	$(RUNTIME) run --rm -it \
		-p $(PORT):$(PORT) \
		-v $(DATA_DIR):/app/data \
		-e OLLAMA_BASE_URL=$${OLLAMA_BASE_URL:-http://host.containers.internal:11434} \
		--name newsbrief $(IMAGE_BASE):$(word 1,$(TAGS))

# ---------- Compose (optional; requires podman-compose or docker-compose shim) ----------
up:
	$(RUNTIME)-compose up -d --build

down:
	$(RUNTIME)-compose down

logs:
	$(RUNTIME)-compose logs -f

# ---------- Defaults ----------
.DEFAULT_GOAL := run
.PHONY: venv run-local build tag push release local-release run up down logs