# ---------- Config ----------
RUNTIME          ?= podman
REGISTRY         ?=                         # e.g. ghcr.io/Deim0s13
IMAGE_NAME       ?= newsbrief-api
PORT             ?= 8790
DATA_DIR         ?= $(PWD)/data
BACKUP_DIR       ?= $(PWD)/backups

# OS detection (Darwin = macOS, Linux covers WSL2 and native Linux)
UNAME_S          := $(shell uname -s)
# 1 when running inside WSL2, 0 on macOS or native Linux
IS_WSL2          := $(shell grep -qi microsoft /proc/version 2>/dev/null && echo 1 || echo 0)

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
	@echo "   Database: PostgreSQL (localhost:5433)"
	@echo "   Production: https://newsbrief.local"
	@echo ""
	@if [ "$(IS_WSL2)" = "1" ]; then \
		pg_isready -h localhost -p 5433 -U newsbrief -d newsbrief >/dev/null 2>&1 || \
			{ echo "❌ PostgreSQL not running. Start it with: make db-up"; exit 1; }; \
	else \
		if ! $(RUNTIME) ps --format "{{.Names}}" 2>/dev/null | grep -q "newsbrief-db-dev"; then \
			echo "❌ PostgreSQL not running. Start it with: make db-up"; \
			echo "   Or use: make dev-full (starts DB + app together)"; \
			exit 1; \
		fi; \
	fi
	ENVIRONMENT=development DATABASE_URL=postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief \
	OLLAMA_BASE_URL=http://localhost:11434 \
		.venv/bin/uvicorn app.main:app --reload --port $(PORT)

dev-full:  ## Start PostgreSQL + development server (single command)
	@echo "🚀 Starting full development environment..."
	@$(MAKE) db-up
	@echo "⏳ Waiting for PostgreSQL to be ready..."
	@if [ "$(IS_WSL2)" = "1" ]; then \
		until pg_isready -h localhost -p 5433 -U newsbrief -d newsbrief >/dev/null 2>&1; do sleep 1; done; \
	else \
		until $(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1; do sleep 1; done; \
	fi
	@echo "✅ PostgreSQL ready"
	@echo ""
	@$(MAKE) dev

# ---------- API Convenience Commands ----------
refresh:  ## Refresh all feeds (fetches new articles)
	@echo "🔄 Refreshing feeds..."
	@curl -s -X POST http://localhost:$(PORT)/refresh | jq . || echo "Error: Is the dev server running? (make dev)"

stories-generate:  ## Generate stories from recent articles
	@echo "📰 Generating stories..."
	@curl -s -X POST http://localhost:$(PORT)/stories/generate \
		-H "Content-Type: application/json" \
		-d '{"time_window_hours": 24, "min_articles_per_story": 2}' | jq . || echo "Error: Is the dev server running? (make dev)"

api-health:  ## Check API health status
	@curl -s http://localhost:$(PORT)/healthz | jq . || echo "Error: Is the dev server running? (make dev)"

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
deploy:                           ## Deploy production stack (start, migrate, auto-create secret)
	@test -f .env || { echo "❌ .env not found — run: make env-init"; exit 1; }
	@echo "🚀 Deploying NewsBrief production stack..."
	@if ! $(RUNTIME) secret inspect db_password >/dev/null 2>&1; then \
		echo "🔑 Creating db_password secret from .env..."; \
		grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2- | \
			$(RUNTIME) secret create db_password -; \
	fi
	@$(RUNTIME)-compose -f compose.yaml -f compose.prod.yaml up -d
	@echo "⏳ Waiting for database..."
	@until $(RUNTIME) exec newsbrief-db pg_isready -U newsbrief -d newsbrief \
		>/dev/null 2>&1; do sleep 1; done
	@echo "🔧 Applying migrations..."
	@$(RUNTIME)-compose -f compose.yaml -f compose.prod.yaml exec -T api alembic upgrade head
	@echo "✅ Running at http://localhost:8787"

deploy-stop:                      ## Stop production stack (preserves data)
	@echo "🛑 Stopping production stack..."
	$(RUNTIME)-compose down
	@echo "✅ Stopped. Data preserved in volumes."

deploy-status:                    ## Check production stack status
	@$(RUNTIME)-compose ps

deploy-init:                      ## Run migrations on production database (also called by make deploy)
	@echo "🔧 Running migrations on production database..."
	$(RUNTIME)-compose -f compose.yaml -f compose.prod.yaml exec -T api alembic upgrade head
	@echo "✅ Database up to date"

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
# On WSL2: uses native PostgreSQL 16 (run make setup-dev-db once to install).
# On macOS: uses a Podman container via compose.dev.yaml (no systemd issues on macOS).

setup-dev-db:                       ## (WSL2) One-time: install native PostgreSQL 16 + pgvector
ifeq ($(IS_WSL2),1)
	@bash scripts/setup-dev-db.sh
else
	@echo "setup-dev-db is for WSL2 only."
	@echo "On macOS, the dev database runs in Podman — use: make db-up"
endif

db-up:                              ## Start PostgreSQL for development (port 5433)
ifeq ($(IS_WSL2),1)
	@echo "🐘 Starting PostgreSQL (native, WSL2)..."
	@if pg_isready -h localhost -p 5433 -U newsbrief -d newsbrief >/dev/null 2>&1; then \
		echo "✅ PostgreSQL already running on localhost:5433"; \
	else \
		sudo service postgresql start && \
		until pg_isready -h localhost -p 5433 -U newsbrief -d newsbrief >/dev/null 2>&1; do sleep 1; done && \
		echo "✅ PostgreSQL running on localhost:5433"; \
	fi
	@echo "   Connection: postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief"
else
	@echo "🐘 Starting PostgreSQL for development..."
	$(RUNTIME)-compose -f compose.dev.yaml up -d
	@echo "✅ PostgreSQL running on localhost:5433"
	@echo "   Connection: postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief"
endif

db-down:                            ## Stop PostgreSQL development database
ifeq ($(IS_WSL2),1)
	@echo "🛑 Stopping native PostgreSQL..."
	@sudo service postgresql stop
	@echo "✅ PostgreSQL stopped"
else
	$(RUNTIME)-compose -f compose.dev.yaml down
endif

db-status:                          ## Check if dev PostgreSQL is running
ifeq ($(IS_WSL2),1)
	@if pg_isready -h localhost -p 5433 -U newsbrief -d newsbrief >/dev/null 2>&1; then \
		echo "✅ PostgreSQL is running (native, port 5433)"; \
		echo "   Status: Ready for connections"; \
	else \
		echo "❌ PostgreSQL not running"; \
		echo "   Start with: make db-up"; \
	fi
else
	@if $(RUNTIME) ps --format "{{.Names}}" 2>/dev/null | grep -q "newsbrief-db-dev"; then \
		echo "✅ PostgreSQL is running (newsbrief-db-dev)"; \
		$(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1 && \
			echo "   Status: Ready for connections" || echo "   Status: Starting..."; \
	else \
		echo "❌ PostgreSQL not running"; \
		echo "   Start with: make db-up"; \
	fi
endif

db-logs:                            ## View PostgreSQL logs
ifeq ($(IS_WSL2),1)
	@sudo journalctl -u 'postgresql*' -f
else
	$(RUNTIME)-compose -f compose.dev.yaml logs -f db
endif

db-psql:                            ## Connect to dev PostgreSQL with psql
ifeq ($(IS_WSL2),1)
	@psql postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief
else
	$(RUNTIME) exec -it newsbrief-db-dev psql -U newsbrief -d newsbrief
endif

db-reset:                           ## Reset development database (WARNING: deletes all data)
	@echo "⚠️  This will delete all development data!"
	@bash -c 'read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ]' || exit 1
ifeq ($(IS_WSL2),1)
	@sudo -u postgres psql -c "DROP DATABASE IF EXISTS newsbrief;"
	@sudo -u postgres psql -c "CREATE DATABASE newsbrief OWNER newsbrief;"
	@sudo -u postgres psql -d newsbrief -c "CREATE EXTENSION IF NOT EXISTS vector;"
	@DATABASE_URL=$(DEV_DATABASE_URL) .venv/bin/alembic upgrade head
	@echo "✅ Database reset and migrations applied"
else
	$(RUNTIME)-compose -f compose.dev.yaml down -v
	$(RUNTIME)-compose -f compose.dev.yaml up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@until $(RUNTIME) exec newsbrief-db-dev pg_isready -U newsbrief -d newsbrief >/dev/null 2>&1; do sleep 1; done
	DATABASE_URL=$(DEV_DATABASE_URL) .venv/bin/alembic upgrade head
	@echo "✅ Database reset and migrations applied"
endif

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
	@bash -c 'read -sp "Enter database password: " pwd && echo && echo "$$pwd" | $(RUNTIME) secret create db_password - && echo "✅ Secret created: db_password"'

secrets-list:  ## List Podman secrets
	$(RUNTIME) secret ls

secrets-delete:  ## Delete database password secret
	$(RUNTIME) secret rm db_password
	@echo "✅ Secret deleted: db_password"

# ---------- Database Migrations ----------
DEV_DATABASE_URL = postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief

migrate:                            ## Run database migrations to latest
	.venv/bin/alembic upgrade head

migrate-dev:                        ## Run migrations on dev database (requires make db-up)
	@echo "Running migrations on dev DB (localhost:5433)..."
	DATABASE_URL=$(DEV_DATABASE_URL) .venv/bin/alembic upgrade head
	@echo "✅ Dev database up to date"

migrate-new:                        ## Create a new migration: make migrate-new MSG="add xyz column"
	@test -n "$(MSG)" || (echo "Set MSG=\"description\"" && exit 1)
	DATABASE_URL=$${DATABASE_URL:-$(DEV_DATABASE_URL)} .venv/bin/alembic revision --autogenerate -m "$(MSG)"

migrate-stamp:                      ## Mark existing DB as current (no migration run)
	DATABASE_URL=$${DATABASE_URL:-$(DEV_DATABASE_URL)} .venv/bin/alembic stamp head

migrate-history:                    ## Show migration history
	.venv/bin/alembic history

migrate-current:                    ## Show current migration version
	DATABASE_URL=$${DATABASE_URL:-$(DEV_DATABASE_URL)} .venv/bin/alembic current

# ---------- Hostname & TLS ----------
HOSTNAME         ?= newsbrief.local
PROJECT_PATH     ?= $(PWD)
PODMAN_COMPOSE   ?= $(shell which podman-compose 2>/dev/null || echo podman-compose)

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
	else \
		echo "❌ $(HOSTNAME) not found in /etc/hosts"; \
		echo "   Run: make hostname-setup"; \
	fi

hostname-remove:                  ## Remove newsbrief.local from /etc/hosts (requires sudo)
	@if grep -q "$(HOSTNAME)" /etc/hosts; then \
		echo "Removing $(HOSTNAME) from /etc/hosts (requires sudo)..."; \
		sudo sed -i.bak '/$(HOSTNAME)/d' /etc/hosts && sudo rm -f /etc/hosts.bak; \
		echo "✅ $(HOSTNAME) removed"; \
	else \
		echo "$(HOSTNAME) not found in /etc/hosts"; \
	fi

CADDY_CONTAINER ?= newsbrief-proxy

hostname-trust-cert:              ## Export Caddy root CA and show command to trust it (macOS only)
ifeq ($(UNAME_S),Darwin)
	@mkdir -p caddy-data
	@if ! podman cp $(CADDY_CONTAINER):/data/caddy/pki/authorities/local/root.crt caddy-data/caddy-root-ca.crt 2>/dev/null; then \
		echo "⚠️  Caddy has not generated a cert yet."; \
		echo "   Open https://$(HOSTNAME) in the browser once, then run: make hostname-trust-cert"; \
		exit 1; \
	fi
	@echo "✅ Exported Caddy root CA to caddy-data/caddy-root-ca.crt"
	@echo "Trust it in macOS Keychain:"
	@echo "  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $(abspath caddy-data/caddy-root-ca.crt)"
else
	@echo "hostname-trust-cert is macOS only."
	@echo "On Linux/WSL2, trust the cert with:"
	@echo "  sudo cp caddy-data/caddy-root-ca.crt /usr/local/share/ca-certificates/newsbrief.crt"
	@echo "  sudo update-ca-certificates"
endif

hostname-regen-certs:             ## Fix ERR_CERT_DATE_INVALID: regenerate Caddy certs
	@echo "Stopping Caddy and clearing old certificates..."
	@podman rm -f $(CADDY_CONTAINER) 2>/dev/null || true
	@rm -rf caddy-data/data/caddy
	@mkdir -p caddy-data/data caddy-data/config
	@echo "Starting Caddy (will generate new certs on first request)..."
	@podman run -d --name $(CADDY_CONTAINER) \
		-p 80:80 -p 443:443 \
		-v $(PWD)/Caddyfile:/etc/caddy/Caddyfile:ro \
		-v $(PWD)/caddy-data/data:/data \
		-v $(PWD)/caddy-data/config:/config \
		caddy:2-alpine
	@echo "✅ Caddy restarted. Next: make hostname-trust-cert"

# ---------- Autostart (app — macOS launchd only) ----------
PLIST_NAME       := com.newsbrief.plist
PLIST_DEST       := $(HOME)/Library/LaunchAgents/$(PLIST_NAME)

autostart-install:                ## Install launchd plist for app auto-start on login (macOS only)
ifeq ($(UNAME_S),Darwin)
	@mkdir -p "$(PROJECT_PATH)/logs"
	@mkdir -p "$$(dirname $(PLIST_DEST))"
	@sed -e 's|__PROJECT_PATH__|$(PROJECT_PATH)|g' \
	     -e 's|__PODMAN_COMPOSE_PATH__|$(PODMAN_COMPOSE)|g' \
	     scripts/com.newsbrief.plist.template > $(PLIST_DEST)
	@launchctl load $(PLIST_DEST)
	@echo "✅ Autostart installed and enabled"
else
	@echo "autostart-install is macOS only. On Windows use Podman Desktop auto-start + Task Scheduler."
endif

autostart-uninstall:              ## Remove launchd plist (macOS only)
ifeq ($(UNAME_S),Darwin)
	@if [ -f "$(PLIST_DEST)" ]; then \
		launchctl unload $(PLIST_DEST) 2>/dev/null || true; \
		rm -f $(PLIST_DEST); \
		echo "✅ Autostart disabled and removed"; \
	else \
		echo "Autostart not installed"; \
	fi
else
	@echo "autostart-uninstall is macOS only."
endif

autostart-status:                 ## Check autostart status (macOS only)
ifeq ($(UNAME_S),Darwin)
	@if [ -f "$(PLIST_DEST)" ]; then \
		echo "✅ Autostart is installed"; \
		launchctl list | grep com.newsbrief || echo "   (not currently loaded)"; \
	else \
		echo "❌ Autostart not installed"; \
		echo "   Run: make autostart-install"; \
	fi
else
	@echo "autostart-status is macOS only."
endif

# ---------- Infrastructure Auto-Start ----------
infra-start:                      ## Manually start k8s infra (kind + ArgoCD + port-forwards)
	@bash scripts/infra-start.sh

infra-autostart-install:          ## Install infra auto-start (launchd on macOS)
ifeq ($(UNAME_S),Darwin)
	@mkdir -p "$(HOME)/Library/LaunchAgents"
	@sed -e 's|__PROJECT_PATH__|$(PROJECT_PATH)|g' \
	     -e 's|__HOME__|$(HOME)|g' \
		launchd/com.newsbrief.infra.plist > "$(HOME)/Library/LaunchAgents/com.newsbrief.infra.plist"
	@launchctl load "$(HOME)/Library/LaunchAgents/com.newsbrief.infra.plist"
	@echo "✅ Infra auto-start installed (macOS launchd)"
	@echo "   The kind cluster + ArgoCD will start automatically on login"
else
	@echo "On Windows: run scripts/infra-task-install.ps1 in PowerShell to register the Task Scheduler task"
	@echo "  powershell.exe -ExecutionPolicy Bypass -File scripts/infra-task-install.ps1"
endif

infra-autostart-uninstall:        ## Remove infra auto-start
ifeq ($(UNAME_S),Darwin)
	@launchctl unload "$(HOME)/Library/LaunchAgents/com.newsbrief.infra.plist" 2>/dev/null || true
	@rm -f "$(HOME)/Library/LaunchAgents/com.newsbrief.infra.plist"
	@echo "✅ Infra auto-start removed"
else
	@echo "On Windows: open Task Scheduler and delete the 'NewsBrief Infrastructure' task"
endif

infra-autostart-status:           ## Check infra auto-start status
ifeq ($(UNAME_S),Darwin)
	@if [ -f "$(HOME)/Library/LaunchAgents/com.newsbrief.infra.plist" ]; then \
		echo "✅ Infra auto-start is installed (macOS launchd)"; \
		launchctl list | grep com.newsbrief.infra || echo "   (not currently loaded)"; \
	else \
		echo "❌ Infra auto-start not installed"; \
		echo "   Run: make infra-autostart-install"; \
	fi
else
	@echo "On Windows: check Task Scheduler for 'NewsBrief Infrastructure' task"
endif

# ---------- Kubernetes Operations (Ansible) ----------
recover:                          ## Recover all services after reboot/sleep
	@echo "🔄 Recovering NewsBrief environment..."
	cd ansible && ansible-playbook -i inventory/localhost.yml playbooks/recover.yml

status:                           ## Check status of all services
	cd ansible && ansible-playbook -i inventory/localhost.yml playbooks/status.yml

port-forwards:                    ## Restart kubectl port-forwards (prod:8788, dev:8789, ArgoCD:8443, Tekton:9097)
	@echo "🔌 Restarting port forwards..."
	@pkill -f "kubectl port-forward" 2>/dev/null || true
	@kubectl port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787 &
	@kubectl port-forward svc/newsbrief -n newsbrief-dev --address 0.0.0.0 8789:8787 &
	@kubectl port-forward svc/argocd-server -n argocd 8443:443 &
	@kubectl port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097 &
	@sleep 2
	@echo "✅ Port forwards active"
	@echo "   Prod (K8s): http://localhost:8788 — https://newsbrief.local via Caddy"
	@echo "   Dev  (K8s): http://localhost:8789"
	@echo "   ArgoCD UI:  https://localhost:8443"
	@echo "   Tekton UI:  http://localhost:9097"

argo-ui:  ## Port-forward Argo CD UI on 8443
	@echo "Open https://localhost:8443"
	kubectl port-forward svc/argocd-server -n argocd 8443:443

# ---------- Compose CD (Windows) ----------
compose-start:  ## Start Compose stack (idempotent — safe to call on boot)
ifneq ($(UNAME_S),Darwin)
	@powershell.exe -ExecutionPolicy Bypass -File scripts/compose-start.ps1
else
	@echo "compose-start is for Windows. On macOS use: make infra-start"
endif

compose-watch:  ## Check GHCR for newer image and redeploy if found
ifneq ($(UNAME_S),Darwin)
	@powershell.exe -ExecutionPolicy Bypass -File scripts/compose-watch.ps1
else
	@echo "compose-watch is for Windows. On macOS CD is handled by ArgoCD."
endif

compose-autostart-install:  ## Install Task Scheduler tasks for Compose auto-deploy (Windows)
ifneq ($(UNAME_S),Darwin)
	@powershell.exe -ExecutionPolicy Bypass -File scripts/compose-task-install.ps1
else
	@echo "compose-autostart-install is for Windows. On macOS use: make infra-autostart-install"
endif

# ---------- Setup ----------
env-init:  ## Create .env from template with generated secure password
	@if [ -f .env ]; then \
		echo "⚠️  .env already exists. Delete it first or edit manually."; \
		exit 1; \
	fi
	@PASSWORD=$$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32) && \
		sed "s/CHANGE_ME_USE_MAKE_ENV_INIT/$$PASSWORD/g" .env.example > .env
	@echo "✅ Created .env — run 'make deploy' to start the stack"
	@echo "📝 Review .env and adjust OLLAMA_BASE_URL if needed"

# ---------- Defaults ----------
.DEFAULT_GOAL := run
.PHONY: venv run-local dev dev-full refresh stories-generate api-health \
	build tag push release local-release clean-release cleanup-old-images run \
	deploy deploy-stop deploy-status deploy-init up down logs \
	setup-dev-db db-up db-down db-status db-logs db-psql db-reset \
	db-backup db-restore db-backup-list \
	secrets-create secrets-list secrets-delete \
	migrate migrate-dev migrate-new migrate-stamp migrate-history migrate-current \
	hostname-setup hostname-check hostname-remove hostname-trust-cert hostname-regen-certs \
	autostart-install autostart-uninstall autostart-status \
	infra-start infra-autostart-install infra-autostart-uninstall infra-autostart-status \
	recover status port-forwards argo-ui \
	compose-start compose-watch compose-autostart-install \
	env-init
