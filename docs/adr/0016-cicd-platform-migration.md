# ADR-0016: CI/CD Platform Migration

## Status
**Accepted** - January 2026

## Context

We currently use GitHub Actions for CI/CD. As part of our cloud-native learning journey, we're evaluating whether to migrate to Tekton Pipelines running on our local Kubernetes cluster.

### Current State (GitHub Actions)

**What works**:
- Automated tests on push/PR
- Familiar YAML syntax
- Good GitHub integration
- Free for public repos

**Pain points**:
- Pipeline failures require push to test fixes
- No local testing of workflows
- Environment differs from production
- Debugging is trial-and-error

### Goals

1. **Local testing** - Run full pipeline before pushing
2. **Environment parity** - Same runtime locally and in production
3. **Learning** - Understand Kubernetes-native CI/CD
4. **No parallel systems** - Don't maintain two CI systems

## Options Considered

### Option 1: Keep GitHub Actions

**Approach**: Fix current issues, don't migrate

| Aspect | Details |
|--------|---------|
| **Effort** | Low (already working) |
| **Local testing** | ❌ Not possible (act has limitations) |
| **K8s integration** | ❌ Separate system |
| **Learning value** | Low |

**Pros**:
- Already working
- Zero migration effort
- Good for open source (contributors know it)

**Cons**:
- Can't test locally
- Different from production environment
- No Kubernetes-native patterns

### Option 2: Tekton Pipelines (Full Migration)

**Approach**: Replace GitHub Actions entirely with Tekton

| Aspect | Details |
|--------|---------|
| **Effort** | High (rebuild all pipelines) |
| **Local testing** | ✅ Full local execution |
| **K8s integration** | ✅ Native |
| **Learning value** | Very high |

**Pros**:
- Same pipeline runs locally and in production
- Kubernetes-native (pods, volumes, etc.)
- Used by enterprise cloud-native teams
- Part of CD Foundation (Linux Foundation)

**Cons**:
- Significant migration effort
- Steeper learning curve
- Less contributor-friendly (fewer know Tekton)
- Need K8s cluster running to test

### Option 3: Hybrid (Tekton + GitHub Actions)

**Approach**: Keep GitHub Actions for PRs, use Tekton for deployment

| Aspect | Details |
|--------|---------|
| **Effort** | Medium |
| **Local testing** | ⚠️ Partial |
| **K8s integration** | ⚠️ Split |
| **Learning value** | Medium |

**Pros**:
- Best of both worlds
- Gradual migration path
- Contributors can still use familiar GitHub Actions

**Cons**:
- Two systems to maintain
- Complexity of keeping them in sync
- User explicitly doesn't want this

### Comparison Matrix

| Criteria | GitHub Actions | Tekton | Hybrid | Weight |
|----------|---------------|--------|--------|--------|
| Local testing | ❌ | ✅ | ⚠️ | High |
| Learning value | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | High |
| K8s-native | ❌ | ✅ | ⚠️ | High |
| Maintenance | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | Medium |
| Enterprise relevance | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Medium |
| Single system | ✅ | ✅ | ❌ | High |

## Decision

**We will migrate fully to Tekton Pipelines**, replacing GitHub Actions.

### Rationale

1. **Learning objective** - This project is about learning cloud-native patterns
2. **No parallel systems** - User explicitly doesn't want to maintain both
3. **Local testing** - Major pain point with current GitHub Actions
4. **Enterprise relevance** - Tekton is used by cloud-native enterprises
5. **Environment parity** - Same pipeline locally and in production

### Trade-offs Accepted

- Higher initial effort
- Need K8s cluster running to test pipelines
- Less familiar to open source contributors

## Implementation

### Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Tekton Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────────┐ │
│  │  Clone  │──▶│  Test   │──▶│  Build  │──▶│  Security   │ │
│  │   Git   │   │ (pytest)│   │ (Image) │   │   Scan      │ │
│  └─────────┘   └─────────┘   └─────────┘   └─────────────┘ │
│                                                      │      │
│                                              ┌───────▼────┐ │
│                                              │   Sign &   │ │
│                                              │    Push    │ │
│                                              └────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
tekton/
├── tasks/
│   ├── git-clone.yaml        # Clone repository
│   ├── python-test.yaml      # Run pytest, mypy, black, isort
│   ├── build-image.yaml      # Build container image
│   ├── trivy-scan.yaml       # Security scanning
│   ├── cosign-sign.yaml      # Image signing
│   └── generate-sbom.yaml    # Software bill of materials
├── pipelines/
│   ├── ci-pipeline.yaml      # Full CI pipeline
│   └── security-pipeline.yaml # Security-only checks
├── triggers/
│   ├── github-listener.yaml  # Listen for GitHub events
│   ├── trigger-binding.yaml  # Extract event data
│   └── trigger-template.yaml # Create PipelineRun
└── runs/
    └── manual-run.yaml       # Manual pipeline trigger
```

### Task: Python Test

```yaml
# tekton/tasks/python-test.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: python-test
spec:
  params:
    - name: python-version
      default: "3.11"
  workspaces:
    - name: source
  steps:
    - name: install
      image: python:$(params.python-version)
      workingDir: $(workspaces.source.path)
      script: |
        pip install -r requirements.txt
        pip install pytest pytest-cov mypy black isort

    - name: lint
      image: python:$(params.python-version)
      workingDir: $(workspaces.source.path)
      script: |
        black --check app/ tests/
        isort --check-only app/ tests/
        mypy app/ --ignore-missing-imports

    - name: test
      image: python:$(params.python-version)
      workingDir: $(workspaces.source.path)
      script: |
        pytest tests/ -v --cov=app --cov-report=xml
```

### Pipeline Definition

```yaml
# tekton/pipelines/ci-pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: newsbrief-ci
spec:
  workspaces:
    - name: source
    - name: docker-config
  params:
    - name: git-url
    - name: git-revision
      default: main
    - name: image-name
      default: newsbrief
  tasks:
    - name: clone
      taskRef:
        name: git-clone
      workspaces:
        - name: output
          workspace: source
      params:
        - name: url
          value: $(params.git-url)
        - name: revision
          value: $(params.git-revision)

    - name: test
      taskRef:
        name: python-test
      runAfter: [clone]
      workspaces:
        - name: source
          workspace: source

    - name: build
      taskRef:
        name: build-image
      runAfter: [test]
      workspaces:
        - name: source
          workspace: source
      params:
        - name: image
          value: $(params.image-name)

    - name: scan
      taskRef:
        name: trivy-scan
      runAfter: [build]
      params:
        - name: image
          value: $(params.image-name)

    - name: sign
      taskRef:
        name: cosign-sign
      runAfter: [scan]
      params:
        - name: image
          value: $(params.image-name)
```

### Makefile Targets

```makefile
# Tekton Pipeline Commands
pipeline-run:     # Run CI pipeline locally
pipeline-status:  # Check pipeline status
pipeline-logs:    # View pipeline logs
pipeline-list:    # List recent runs
```

### Migration Plan

| Phase | Action | GitHub Actions |
|-------|--------|----------------|
| 1 | Create Tekton tasks | Keep running |
| 2 | Test pipeline locally | Keep running |
| 3 | Add Tekton Triggers | Keep running |
| 4 | Verify equivalent | Keep running |
| 5 | Remove GitHub Actions | **Delete** |

## Consequences

### Positive
- Full local pipeline testing before push
- Same environment locally and in production
- Deep understanding of Kubernetes-native CI/CD
- Enterprise-relevant skills

### Negative
- Need K8s cluster running to test
- More complex initial setup
- Less familiar to contributors

### Neutral
- Different YAML syntax to learn
- Pipeline debugging moves from GitHub UI to kubectl/tkn

## References

- [Tekton Documentation](https://tekton.dev/docs/)
- [Tekton Hub (Task Catalog)](https://hub.tekton.dev/)
- [Tekton Tutorial](https://tekton.dev/docs/getting-started/)
- [CD Foundation](https://cd.foundation/)
