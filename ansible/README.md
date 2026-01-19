# NewsBrief Ansible Playbooks

Operational procedures for managing the NewsBrief development environment on a laptop.

## Prerequisites

```bash
# Install Ansible (macOS)
brew install ansible

# Or via pip
pip install ansible
```

## Quick Start

After a laptop reboot or wake from sleep:

```bash
# Full recovery - checks and restarts all services
make recover

# Or directly with Ansible
cd ansible
ansible-playbook -i inventory/localhost.yml playbooks/recover.yml
```

## Playbooks

### `recover.yml` - Full Environment Recovery

Checks and restarts all services in the correct order:

1. **Podman** - Starts the container runtime
2. **Kind** - Creates/verifies the Kubernetes cluster
3. **Tekton** - Installs pipelines, triggers, dashboard
4. **ArgoCD** - Installs GitOps controller and apps
5. **NewsBrief** - Sets up port forwards and seeds dev data
6. **Caddy** - Starts the HTTPS reverse proxy

```bash
ansible-playbook -i inventory/localhost.yml playbooks/recover.yml
```

### `status.yml` - Check Service Status

Reports the current state of all services without making changes:

```bash
ansible-playbook -i inventory/localhost.yml playbooks/status.yml
```

## Common Scenarios

### After Laptop Reboot

```bash
make recover
```

### After Wake from Sleep

Usually only port forwards need restarting:

```bash
# Quick port forward restart
make port-forwards

# Or full recovery if things are broken
make recover
```

### Check What's Running

```bash
make status
```

### Force Full Recreate

If things are badly broken:

```bash
ansible-playbook -i inventory/localhost.yml playbooks/recover.yml -e force_recreate=true
```

## Service URLs

After recovery, services are available at:

| Service | URL | Notes |
|---------|-----|-------|
| **Dev** | http://localhost:8787 | Run `make dev` locally |
| **Prod** | https://newsbrief.local | Kubernetes via Caddy |
| Tekton Dashboard | http://localhost:9097 | Port-forwarded |
| Event Listener | http://localhost:8080 | Port-forwarded |

**Note**: Dev runs locally (not in Kubernetes). Run `make dev` to start the development server.

## Troubleshooting

### Podman won't start

```bash
podman machine stop
podman machine start
```

### Kind cluster is broken

```bash
kind delete cluster --name newsbrief-dev
./scripts/setup-kind-registry.sh
```

### Port forwards not working

```bash
pkill -f "kubectl port-forward"
make port-forwards
```

### Caddy certificate issues

```bash
podman rm -f newsbrief-proxy
# Then run recover
make recover
```
