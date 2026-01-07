# ---------- Config ----------
RUNTIME          ?= podman
REGISTRY         ?=                         # e.g. ghcr.io/Deim0s13
IMAGE_NAME       ?= newsbrief-api
PORT             ?= 8787
DATA_DIR         ?= $(PWD)/data
BACKUP_DIR       ?= $(PWD)/backups

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
	.venv/bin/uvicorn app.main:app --reload --port $(PORT)

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

# ---------- Cleanup helpers ----------
cleanup-old-images:               ## Remove old image versions (keeps current + 1 previous)
	@echo "🧹 Cleaning up old newsbrief images..."
	@# Stop and remove any running newsbrief containers
	-$(RUNTIME) stop newsbrief 2>/dev/null || true
	-$(RUNTIME) rm newsbrief 2>/dev/null || true
	@# Get current image ID to protect it
	@CURRENT_ID=$$($(RUNTIME) images --format "{{.ID}}" localhost/newsbrief-api:buildcache 2>/dev/null || echo ""); \
	if [ -n "$$CURRENT_ID" ]; then \
		echo "🛡️  Protecting current image: $$CURRENT_ID"; \
		$(RUNTIME) images localhost/newsbrief-api --format "{{.Repository}}:{{.Tag}} {{.ID}}" | \
		while read -r tag id; do \
			if [ "$$tag" != "localhost/newsbrief-api:buildcache" ] && [ "$$id" != "$$CURRENT_ID" ]; then \
				echo "🗑️  Removing old image: $$tag ($$id)"; \
				$(RUNTIME) rmi "$$tag" 2>/dev/null || true; \
			fi; \
		done; \
	fi
	@# Clean up any orphaned images and build cache
	-$(RUNTIME) system prune -f >/dev/null 2>&1
	@echo "✅ Cleanup complete!"

# Convenience targets
release:                          ## Example: make release VERSION=v0.2.0 REGISTRY=ghcr.io/deim0s13
	@test -n "$(VERSION)" || (echo "Set VERSION=vX.Y.Z" && exit 1)
	$(MAKE) push

local-release:                    ## Build and tag locally: make local-release VERSION=v0.2.0 [CLEANUP=true]
	@test -n "$(VERSION)" || (echo "Set VERSION=vX.Y.Z" && exit 1)
	@if [ "$(CLEANUP)" = "true" ]; then $(MAKE) cleanup-old-images; fi
	$(MAKE) tag
	@if [ "$(CLEANUP)" = "true" ]; then echo "🎉 Released $(VERSION) with cleanup!"; else echo "💡 Tip: Use CLEANUP=true to auto-remove old images"; fi

clean-release:                    ## Build new version and auto-cleanup old images
	@test -n "$(VERSION)" || (echo "Set VERSION=vX.Y.Z" && exit 1)
	$(MAKE) cleanup-old-images
	$(MAKE) tag
	@echo "🎉 Released $(VERSION) with automatic cleanup!"

run:
	$(RUNTIME) run --rm -it \
		-p $(PORT):$(PORT) \
		-v $(DATA_DIR):/app/data \
		-e OLLAMA_BASE_URL=$${OLLAMA_BASE_URL:-http://host.containers.internal:11434} \
		--name newsbrief $(IMAGE_BASE):$(word 1,$(TAGS))

# ---------- Production Deployment ----------
deploy:                           ## Deploy production stack (containers + PostgreSQL)
	@echo "🚀 Deploying NewsBrief production stack..."
	$(RUNTIME)-compose up -d --build
	@echo "✅ Production deployed at http://localhost:$(PORT)"
	@echo "📊 View logs: make logs"

deploy-stop:                      ## Stop production stack (preserves data)
	@echo "🛑 Stopping production stack..."
	$(RUNTIME)-compose down
	@echo "✅ Stopped. Data preserved in volumes."

deploy-status:                    ## Check production stack status
	@$(RUNTIME)-compose ps

deploy-init:                      ## First-time setup: run migrations on fresh database
	@echo "🔧 Initializing production database..."
	$(RUNTIME)-compose exec api alembic upgrade head
	@echo "✅ Database initialized"

# ---------- Compose (dev/debugging) ----------
up:
	$(RUNTIME)-compose up -d --build

down:
	$(RUNTIME)-compose down

logs:
	$(RUNTIME)-compose logs -f

# ---------- Database (PostgreSQL) ----------
db-up:                              ## Start PostgreSQL container only
	$(RUNTIME)-compose up db -d

db-down:                            ## Stop PostgreSQL container
	$(RUNTIME)-compose stop db

db-logs:                            ## View PostgreSQL logs
	$(RUNTIME)-compose logs -f db

db-psql:                            ## Connect to PostgreSQL with psql
	$(RUNTIME) exec -it newsbrief-db psql -U newsbrief -d newsbrief

db-reset:                           ## Reset PostgreSQL database (WARNING: deletes all data)
	$(RUNTIME)-compose down -v
	$(RUNTIME)-compose up db -d
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 5
	. .venv/bin/activate && . .env && DATABASE_URL="$$DATABASE_URL" alembic upgrade head
	@echo "✅ Database reset and migrations applied"

# ---------- Database Backup/Restore ----------
db-backup:                          ## Backup production database to BACKUP_DIR
	@mkdir -p "$(BACKUP_DIR)"
	@BACKUP_FILE="$(BACKUP_DIR)/newsbrief-$$(date +%Y%m%d-%H%M%S).sql"; \
	$(RUNTIME) exec newsbrief-db pg_dump -U newsbrief newsbrief > "$$BACKUP_FILE"; \
	echo "✅ Backup saved to $$BACKUP_FILE"

db-restore:                         ## Restore from backup: make db-restore FILE=path/to/backup.sql
	@test -n "$(FILE)" || (echo "Usage: make db-restore FILE=path/to/backup.sql" && exit 1)
	@test -f "$(FILE)" || (echo "File not found: $(FILE)" && exit 1)
	$(RUNTIME) exec -i newsbrief-db psql -U newsbrief newsbrief < "$(FILE)"
	@echo "✅ Restored from $(FILE)"

db-backup-list:                     ## List available backups
	@ls -lah "$(BACKUP_DIR)"/*.sql 2>/dev/null || echo "No backups found in $(BACKUP_DIR)/"

# ---------- Database Migrations ----------
migrate:                            ## Run database migrations to latest
	.venv/bin/alembic upgrade head

migrate-new:                        ## Create a new migration: make migrate-new MSG="add xyz column"
	@test -n "$(MSG)" || (echo "Set MSG=\"description\"" && exit 1)
	.venv/bin/alembic revision --autogenerate -m "$(MSG)"

migrate-stamp:                      ## Mark existing DB as current (no migration run)
	.venv/bin/alembic stamp head

migrate-history:                    ## Show migration history
	.venv/bin/alembic history

migrate-current:                    ## Show current migration version
	.venv/bin/alembic current

# ---------- Defaults ----------
.DEFAULT_GOAL := run
.PHONY: venv run-local build tag push release local-release clean-release cleanup-old-images run deploy deploy-stop deploy-status deploy-init up down logs db-up db-down db-logs db-psql db-reset db-backup db-restore db-backup-list migrate migrate-new migrate-stamp migrate-history migrate-current
