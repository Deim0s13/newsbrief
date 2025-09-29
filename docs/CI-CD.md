# CI/CD & GitOps Documentation

## Overview

NewsBrief uses a comprehensive CI/CD pipeline with GitOps practices to ensure reliable, secure, and automated deployments.

## Workflow Architecture

### 📋 Main CI/CD Pipeline (`ci-cd.yml`)

**Triggers:**
- Push to `main` or `dev` branches
- Pull requests to `main`
- Published releases

**Jobs:**
1. **🧪 Test & Quality** - Code quality, linting, security scanning
2. **🔨 Build Container** - Multi-arch container builds with caching
3. **🔒 Security Scan** - Vulnerability scanning with Trivy
4. **🚀 Deploy** - Environment-specific deployments
5. **📦 Release Assets** - Automated release creation

### 🔄 Dependency Management (`dependencies.yml`)

**Schedule:** Weekly (Mondays at 09:00 UTC)

**Features:**
- Automated Python dependency updates
- Security vulnerability scanning
- Base Docker image updates
- Automated PR creation for updates

### 🎯 Project Automation (`project-automation.yml`)

**Triggers:**
- Issue lifecycle events (opened, closed, labeled, assigned)
- Pull request events (opened, ready_for_review, closed)

**Features:**
- Automatic project board synchronization
- Status field updates based on issue/PR state
- Epic assignment from labels (`epic:*`)
- Graceful error handling

### 🚀 GitOps Deployment (`gitops-deploy.yml`)

**Triggers:**
- Manual dispatch
- Called by other workflows

**Features:**
- Environment-specific configurations
- Kubernetes manifest generation
- Health checks and validation
- Deployment tracking

## Environment Configuration

### Development (`dev`)
- **Replicas:** 1
- **Resources:** 100m CPU, 256Mi Memory
- **Database:** 1Gi storage
- **Domain:** `newsbrief-dev.internal`
- **Backup:** Disabled

### Staging (`staging`)
- **Replicas:** 2
- **Resources:** 200m CPU, 512Mi Memory
- **Database:** 5Gi storage
- **Domain:** `newsbrief-staging.internal`
- **Backup:** Enabled

### Production (`prod`)
- **Replicas:** 3
- **Resources:** 500m CPU, 1Gi Memory
- **Database:** 20Gi storage
- **Domain:** `newsbrief.example.com`
- **Backup:** Enabled

## Security Features

### 🔒 Security Scanning
- **Trivy** vulnerability scanning for containers
- **Safety** dependency security auditing
- **Super-Linter** code quality scanning
- SARIF upload to GitHub Security tab

### 🛡️ Security Best Practices
- Multi-stage Docker builds
- Non-root container execution
- Minimal base images
- Secrets management via GitHub Secrets
- GITHUB_TOKEN permission restrictions

## Container Registry

Images are published to GitHub Container Registry (GHCR):
- **Registry:** `ghcr.io`
- **Repository:** `ghcr.io/deim0s13/newsbrief`
- **Supported Platforms:** `linux/amd64`, `linux/arm64`

### Image Tags
- `main` - Latest stable from main branch
- `dev` - Latest development from dev branch
- `v1.2.3` - Semantic version tags
- `pr-123` - Pull request builds
- `main-abc1234` - Commit-based tags

## Deployment Process

### Automatic Deployments
1. **Development:** Auto-deploy on push to `dev`
2. **Staging:** Auto-deploy on push to `main`
3. **Production:** Auto-deploy on published release

### Manual Deployments
```bash
# Deploy specific version to environment
gh workflow run gitops-deploy.yml \
  -f environment=prod \
  -f image_tag=ghcr.io/deim0s13/newsbrief:v0.3.4 \
  -f version=v0.3.4
```

## Monitoring & Observability

### Health Checks
- **Liveness Probe:** HTTP GET `/` (30s delay)
- **Readiness Probe:** HTTP GET `/` (5s delay)
- **Prometheus Metrics:** Exposed on port 8787

### Deployment Tracking
- Deployment records in JSON format
- Timestamp, version, and configuration tracking
- Integration with GitHub Deployments API

## Development Workflow

### Branch Strategy
```
main (production)
 ├── staging (pre-production)
 └── dev (development)
     ├── feature/new-feature
     └── bugfix/fix-issue
```

### Pull Request Process
1. Create feature branch from `dev`
2. Implement changes and tests
3. Open PR to `dev` branch
4. Automated CI/CD runs:
   - Code quality checks
   - Security scanning
   - Container build
5. Review and merge
6. Auto-deploy to development environment

### Release Process
1. Merge `dev` → `main` when ready for release
2. Create and publish GitHub release
3. Automated deployment to staging and production
4. Monitor deployment health

## Environment Variables

### Core Application
```yaml
ENVIRONMENT: dev|staging|prod
DATABASE_URL: sqlite:///app/data/newsbrief.sqlite3
OLLAMA_BASE_URL: http://ollama:11434
```

### AI Configuration
```yaml
NEWSBRIEF_LLM_MODEL: llama3.2:3b
NEWSBRIEF_CHUNKING_THRESHOLD: 3000
NEWSBRIEF_CHUNK_SIZE: 1500
NEWSBRIEF_MAX_CHUNK_SIZE: 2000
NEWSBRIEF_CHUNK_OVERLAP: 200
```

### Feed Processing
```yaml
NEWSBRIEF_MAX_ITEMS_PER_REFRESH: 150
NEWSBRIEF_MAX_ITEMS_PER_FEED: 20
NEWSBRIEF_MAX_REFRESH_TIME: 300
```

## Troubleshooting

### Common Issues

**Workflow Failures:**
```bash
# Check workflow status
gh run list --workflow=ci-cd.yml --limit 5

# View specific run logs
gh run view <run-id> --log
```

**Project Automation Issues:**
- Verify project number in workflow environment
- Check GITHUB_TOKEN permissions
- Ensure project fields exist (Status, Epic)

**Deployment Issues:**
- Validate image exists in registry
- Check environment configuration
- Review resource quotas and limits

### Debug Commands

```bash
# Test container locally
podman run --rm -p 8787:8787 ghcr.io/deim0s13/newsbrief:latest

# Check deployment status
kubectl get deployments -n newsbrief-prod

# View pod logs
kubectl logs -f deployment/newsbrief-prod -n newsbrief-prod
```

## Contributing to CI/CD

### Adding New Workflows
1. Create workflow file in `.github/workflows/`
2. Follow naming convention: `purpose-description.yml`
3. Add comprehensive documentation
4. Test with workflow_dispatch trigger
5. Update this documentation

### Modifying Existing Workflows
1. Test changes in feature branch
2. Use `workflow_dispatch` for manual testing
3. Monitor run results carefully
4. Update documentation accordingly

### Best Practices
- Use `continue-on-error` for non-critical steps
- Add comprehensive logging and error messages
- Cache dependencies when possible
- Use secrets for sensitive data
- Follow principle of least privilege

## Security Considerations

### Secret Management
- Store sensitive values in GitHub Secrets
- Use environment-specific secrets
- Rotate secrets regularly
- Limit secret access scope

### Container Security
- Scan images for vulnerabilities
- Use official base images
- Run as non-root user
- Minimize attack surface

### Access Control
- Restrict workflow permissions
- Use environment protection rules
- Require reviews for production deployments
- Audit deployment activities

## Future Improvements

### Planned Features
- **ArgoCD Integration** - GitOps deployment controller
- **Helm Charts** - Kubernetes package management
- **Istio Service Mesh** - Advanced traffic management
- **Grafana Dashboards** - Enhanced observability
- **Automated Testing** - Integration and E2E tests
- **Blue/Green Deployments** - Zero-downtime updates
- **Canary Releases** - Gradual rollout strategy

### Monitoring Enhancements
- Application performance monitoring (APM)
- Error tracking and alerting
- Log aggregation and analysis
- Custom business metrics

---

For questions or support, please open an issue or contact the development team.
