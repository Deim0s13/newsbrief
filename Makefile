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

dev:  ## Run development server (requires PostgreSQL - see make db-up)
	@echo "🔧 Starting development server on http://localhost:$(PORT)"
	@echo "   Database: PostgreSQL (localhost:5432)"
	@echo "   Production: https://newsbrief.local"
	@echo ""
	@# Check if PostgreSQL is running
	@if ! $(RUNTIME) ps --format "{{.Names}}" 2>/dev/null | grep -q "newsbrief-db-dev"; then \
		echo "❌ PostgreSQL not running. Start it with: make db-up"; \
		echo "   Or use: make dev-full (starts DB + app together)"; \
		exit 1; \
	fi
	ENVIRONMENT=development DATABASE_URL=postgresql://newsbrief:newsbrief_dev@localhost:5432/newsbrief \
		.venv/bin/uvicorn app.main:app --reload --port $(PORT)

dev-full:  ## Start PostgreSQL + development server (single command)
	@echo "🚀 Starting full development environment..."
	@$(MAKE) db-up
	@echo "⏳ Waiting for PostgreSQL to be ready..."
	@until $(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "✅ PostgreSQL ready"
	@echo ""
	@$(MAKE) dev

env-init:  ## Create .env from template with generated secure password
	@if [ -f .env ]; then \
		echo "⚠️  .env already exists. Delete it first or edit manually."; \
		exit 1; \
	fi
	@cp .env.example .env
	@PASSWORD=$$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32) && \
		sed -i '' "s/CHANGE_ME_USE_MAKE_ENV_INIT/$$PASSWORD/" .env
	@echo "✅ Created .env with secure generated password"
	@echo "📝 Review .env and adjust OLLAMA_BASE_URL if needed"

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
	@if $(RUNTIME) secret inspect db_password >/dev/null 2>&1; then \
		echo "🔐 Using Podman Secrets for database credentials"; \
		$(RUNTIME)-compose -f compose.yaml -f compose.prod.yaml up -d --build; \
	else \
		echo "⚠️  No secret found - using .env file (run 'make secrets-create' for production)"; \
		$(RUNTIME)-compose up -d --build; \
	fi
	@echo "✅ Production deployed at https://$(HOSTNAME)"
	@echo "   (Development: make dev → http://localhost:$(PORT))"
	@echo "📊 View logs: make deploy-logs"

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
	@if $(RUNTIME) secret inspect db_password >/dev/null 2>&1; then \
		$(RUNTIME)-compose -f compose.yaml -f compose.prod.yaml up -d --build; \
	else \
		$(RUNTIME)-compose up -d --build; \
	fi

down:
	$(RUNTIME)-compose down

logs:
	$(RUNTIME)-compose logs -f

# ---------- Database (PostgreSQL for Development) ----------
db-up:                              ## Start PostgreSQL for development
	@echo "🐘 Starting PostgreSQL for development..."
	$(RUNTIME)-compose -f compose.dev.yaml up -d
	@echo "✅ PostgreSQL running on localhost:5432"
	@echo "   Connection: postgresql://newsbrief:newsbrief_dev@localhost:5432/newsbrief"

db-down:                            ## Stop PostgreSQL development container
	$(RUNTIME)-compose -f compose.dev.yaml down

db-status:                          ## Check if dev PostgreSQL is running
	@if $(RUNTIME) ps --format "{{.Names}}" 2>/dev/null | grep -q "newsbrief-db-dev"; then \
		echo "✅ PostgreSQL is running (newsbrief-db-dev)"; \
		$(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1 && \
			echo "   Status: Ready for connections" || echo "   Status: Starting..."; \
	else \
		echo "❌ PostgreSQL not running"; \
		echo "   Start with: make db-up"; \
	fi

db-logs:                            ## View PostgreSQL logs
	$(RUNTIME)-compose -f compose.dev.yaml logs -f db

db-psql:                            ## Connect to PostgreSQL with psql
	$(RUNTIME) exec -it newsbrief-db-dev psql -U newsbrief -d newsbrief

db-reset:                           ## Reset development database (WARNING: deletes all data)
	@echo "⚠️  This will delete all development data!"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(RUNTIME)-compose -f compose.dev.yaml down -v
	$(RUNTIME)-compose -f compose.dev.yaml up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@until $(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1; do sleep 1; done
	DATABASE_URL=postgresql://newsbrief:newsbrief_dev@localhost:5432/newsbrief .venv/bin/alembic upgrade head
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

# ---------- Secrets Management (Production) ----------
secrets-create:  ## Create Podman secret for database password
	@echo "Creating Podman secret for database password..."
	@read -sp "Enter database password: " pwd && echo && \
		echo "$$pwd" | $(RUNTIME) secret create db_password - && \
		echo "✅ Secret created: db_password"

secrets-list:  ## List Podman secrets
	$(RUNTIME) secret ls

secrets-delete:  ## Delete database password secret
	$(RUNTIME) secret rm db_password
	@echo "✅ Secret deleted: db_password"

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

# ---------- Hostname & Autostart ----------
HOSTNAME         ?= newsbrief.local
PROJECT_PATH     ?= $(PWD)
PODMAN_COMPOSE   ?= $(shell which podman-compose 2>/dev/null || echo /opt/homebrew/bin/podman-compose)
PLIST_NAME       := com.newsbrief.plist
PLIST_DEST       := $(HOME)/Library/LaunchAgents/$(PLIST_NAME)

hostname-setup:                   ## Add newsbrief.local to /etc/hosts (requires sudo)
	@if grep -q "$(HOSTNAME)" /etc/hosts; then \
		echo "✅ $(HOSTNAME) already configured in /etc/hosts"; \
	else \
		echo "Adding $(HOSTNAME) to /etc/hosts (requires sudo)..."; \
		echo "127.0.0.1   $(HOSTNAME)" | sudo tee -a /etc/hosts > /dev/null; \
		echo "✅ $(HOSTNAME) added to /etc/hosts"; \
	fi

hostname-check:                   ## Verify hostname is configured
	@if grep -q "$(HOSTNAME)" /etc/hosts; then \
		echo "✅ $(HOSTNAME) is configured"; \
		echo "   Access production at: http://$(HOSTNAME)"; \
	else \
		echo "❌ $(HOSTNAME) not found in /etc/hosts"; \
		echo "   Run: make hostname-setup"; \
	fi

hostname-remove:                  ## Remove newsbrief.local from /etc/hosts (requires sudo)
	@if grep -q "$(HOSTNAME)" /etc/hosts; then \
		echo "Removing $(HOSTNAME) from /etc/hosts (requires sudo)..."; \
		sudo sed -i '' '/$(HOSTNAME)/d' /etc/hosts; \
		echo "✅ $(HOSTNAME) removed"; \
	else \
		echo "$(HOSTNAME) not found in /etc/hosts"; \
	fi

# ---------- Autostart (launchd) ----------
autostart-install:                ## Install launchd plist for auto-start on login
	@mkdir -p "$(PROJECT_PATH)/logs"
	@mkdir -p "$$(dirname $(PLIST_DEST))"
	@sed -e 's|__PROJECT_PATH__|$(PROJECT_PATH)|g' \
	     -e 's|__PODMAN_COMPOSE_PATH__|$(PODMAN_COMPOSE)|g' \
	     scripts/com.newsbrief.plist.template > $(PLIST_DEST)
	@launchctl load $(PLIST_DEST)
	@echo "✅ Autostart installed and enabled"
	@echo "   NewsBrief will start automatically on login"
	@echo "   Logs: $(PROJECT_PATH)/logs/"

autostart-uninstall:              ## Remove launchd plist (disable auto-start)
	@if [ -f "$(PLIST_DEST)" ]; then \
		launchctl unload $(PLIST_DEST) 2>/dev/null || true; \
		rm -f $(PLIST_DEST); \
		echo "✅ Autostart disabled and removed"; \
	else \
		echo "Autostart not installed"; \
	fi

autostart-status:                 ## Check autostart status
	@if [ -f "$(PLIST_DEST)" ]; then \
		echo "✅ Autostart is installed"; \
		launchctl list | grep com.newsbrief || echo "   (not currently loaded)"; \
	else \
		echo "❌ Autostart not installed"; \
		echo "   Run: make autostart-install"; \
	fi

autostart-start:                  ## Manually trigger autostart (for testing)
	@launchctl start com.newsbrief
	@echo "✅ Triggered com.newsbrief"

autostart-stop:                   ## Stop the launchd job
	@launchctl stop com.newsbrief 2>/dev/null || true
	@echo "✅ Stopped com.newsbrief"

# ---------- Kubernetes Operations (Ansible) ----------
recover:                          ## Recover all services after reboot/sleep
	@echo "🔄 Recovering NewsBrief environment..."
	cd ansible && ansible-playbook -i inventory/localhost.yml playbooks/recover.yml

status:                           ## Check status of all services
	cd ansible && ansible-playbook -i inventory/localhost.yml playbooks/status.yml

port-forwards:                    ## Restart port forwards for prod/Tekton (dev is local)
	@echo "🔌 Restarting port forwards..."
	@pkill -f "kubectl port-forward" 2>/dev/null || true
	@kubectl port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787 &
	@kubectl port-forward svc/el-newsbrief-listener 8080:8080 &
	@kubectl port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097 &
	@sleep 2
	@echo "✅ Port forwards restarted"
	@echo "   Prod:    http://localhost:8788 (https://newsbrief.local via Caddy)"
	@echo "   Tekton:  http://localhost:9097"
	@echo ""
	@echo "   Dev: Run 'make dev' locally → http://localhost:8787"

smee:                             ## Start smee webhook bridge
	npx smee-client --url https://smee.io/cddqBCYHwHG3ZcUY --target http://localhost:8080 --path /

# ---------- Defaults ----------
.DEFAULT_GOAL := run
.PHONY: venv run-local dev dev-full build tag push release local-release clean-release cleanup-old-images run deploy deploy-stop deploy-status deploy-init up down logs db-up db-down db-status db-logs db-psql db-reset db-backup db-restore db-backup-list migrate migrate-new migrate-stamp migrate-history migrate-current hostname-setup hostname-check hostname-remove autostart-install autostart-uninstall autostart-status autostart-start autostart-stop recover status port-forwards smee
