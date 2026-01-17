# ADR-0018: Secure Supply Chain Strategy

## Status
**Accepted** - January 2026

## Context

Software supply chain security has become critical. High-profile attacks (SolarWinds, Log4Shell, codecov) have shown that attackers target the build and delivery process, not just runtime.

As a modern startup mindset, we want to build security into our CI/CD from day one, not bolt it on later.

### Supply Chain Attack Vectors

| Vector | Example | Mitigation |
|--------|---------|------------|
| Compromised dependencies | Log4Shell | Dependency scanning |
| Tampered images | Codecov | Image signing |
| Unknown components | Audit requirements | SBOM generation |
| Base image vulnerabilities | Alpine CVEs | Container scanning |
| Secrets in images | API keys in layers | Secret scanning |

### Compliance Drivers

- **Executive Order 14028** (US) - Requires SBOM for government software
- **EU Cyber Resilience Act** - SBOM mandatory for products sold in EU
- **SOC 2 / ISO 27001** - Supply chain security controls expected

## Goals

1. **Scan dependencies** - Catch known vulnerabilities before deploy
2. **Scan containers** - Detect OS/package vulnerabilities
3. **Sign images** - Cryptographically verify image integrity
4. **Generate SBOM** - Know what's in our software
5. **Automated** - Security checks in every pipeline run

## Options Considered

### Container/Dependency Scanning

#### Trivy (Aqua Security)

| Aspect | Details |
|--------|---------|
| **License** | Apache 2.0 (free) |
| **Scans** | Containers, filesystems, git repos, Kubernetes |
| **Databases** | NVD, Alpine, Red Hat, Debian, Python, Node, etc. |
| **Speed** | Fast (local DB cache) |
| **CI Integration** | Excellent |
| **SBOM output** | ✅ CycloneDX, SPDX |

#### Grype (Anchore)

| Aspect | Details |
|--------|---------|
| **License** | Apache 2.0 (free) |
| **Scans** | Containers, filesystems |
| **Speed** | Fast |
| **Pairs with** | Syft (SBOM generator) |

#### Snyk

| Aspect | Details |
|--------|---------|
| **License** | Freemium (limited free tier) |
| **Scans** | Code, containers, IaC, dependencies |
| **Features** | Fix suggestions, monitoring |
| **Cost** | $$ for full features |

**Decision**: **Trivy** - Free, comprehensive, excellent SBOM support

### Image Signing

#### Cosign (Sigstore)

| Aspect | Details |
|--------|---------|
| **License** | Apache 2.0 (free) |
| **Approach** | Keyless or key-based signing |
| **Transparency** | Rekor transparency log |
| **Verification** | Kubernetes admission controllers |
| **Adoption** | Kubernetes, distroless, chainguard |

#### Cosign Signing Modes

| Mode | Requirements | Use Case |
|------|--------------|----------|
| **Keyless (OIDC)** | OIDC provider (GitHub Actions, Dex, etc.) | CI/CD with OIDC identity |
| **Key-based** | Generated key pair, secure key storage | Local dev, air-gapped, simpler setup |

**Local Development Decision**: Use **key-based signing** because:
- No OIDC provider available in local kind cluster
- Simpler setup, faster to implement
- Keys stored as Kubernetes secrets
- Can upgrade to keyless later if OIDC provider deployed

**Future consideration**: Deploy Dex or Sigstore scaffold for keyless signing.

#### Notary v2 (CNCF)

| Aspect | Details |
|--------|---------|
| **License** | Apache 2.0 |
| **Status** | Newer, less mature |
| **Integration** | OCI registries |

**Decision**: **Cosign** - Industry standard, key-based for local, keyless upgrade path

### SBOM Generation

#### Trivy (built-in)

Generate SBOM as part of scanning.

#### Syft (Anchore)

Dedicated SBOM tool, pairs with Grype.

**Decision**: **Trivy** - Already using for scanning, does SBOM too

## Decision

**We will implement a secure supply chain using:**

| Component | Tool | Purpose |
|-----------|------|---------|
| **Vulnerability Scanning** | Trivy | Containers, dependencies, IaC |
| **Image Signing** | Cosign | Cryptographic verification |
| **SBOM Generation** | Trivy | CycloneDX format |
| **Secret Detection** | Trivy | Detect leaked secrets |

### Rationale

1. **Trivy does it all** - Scanning, SBOM, secrets in one tool
2. **Cosign is the standard** - Used by all major projects
3. **Free and open source** - No licensing costs
4. **Tekton integration** - Official Tekton Hub tasks available
5. **Startup mindset** - Security from day one, not technical debt

## Implementation

### Pipeline Integration

```
┌─────────────────────────────────────────────────────────────┐
│                   Secure CI Pipeline                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────────┐ │
│  │  Clone  │──▶│  Test   │──▶│  Build  │──▶│   Trivy     │ │
│  │         │   │         │   │  Image  │   │   Scan      │ │
│  └─────────┘   └─────────┘   └─────────┘   └─────────────┘ │
│                                                     │       │
│       ┌─────────────────────────────────────────────┘       │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │  Generate   │──▶│   Cosign    │──▶│    Push     │       │
│  │   SBOM      │   │    Sign     │   │   to Reg    │       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Tekton Task: Trivy Scan

```yaml
# tekton/tasks/trivy-scan.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: trivy-scan
spec:
  params:
    - name: image
      description: Image to scan
    - name: severity
      default: "HIGH,CRITICAL"
    - name: exit-code
      default: "1"  # Fail on vulnerabilities
  results:
    - name: vulnerabilities
      description: Number of vulnerabilities found
  steps:
    - name: scan
      image: aquasec/trivy:latest
      script: |
        # Scan image for vulnerabilities
        trivy image \
          --severity $(params.severity) \
          --exit-code $(params.exit-code) \
          --format table \
          $(params.image)

    - name: scan-config
      image: aquasec/trivy:latest
      script: |
        # Scan for misconfigurations
        trivy config \
          --severity $(params.severity) \
          .

    - name: scan-secrets
      image: aquasec/trivy:latest
      script: |
        # Scan for exposed secrets
        trivy fs \
          --scanners secret \
          --exit-code 1 \
          .
```

### Tekton Task: Generate SBOM

```yaml
# tekton/tasks/generate-sbom.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: generate-sbom
spec:
  params:
    - name: image
  workspaces:
    - name: output
  steps:
    - name: generate
      image: aquasec/trivy:latest
      script: |
        # Generate SBOM in CycloneDX format
        trivy image \
          --format cyclonedx \
          --output $(workspaces.output.path)/sbom.json \
          $(params.image)

        echo "SBOM generated: $(workspaces.output.path)/sbom.json"
```

### Tekton Task: Cosign Sign (Key-based)

```yaml
# tekton/tasks/sign-image.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: sign-image
spec:
  params:
    - name: image
  steps:
    - name: sign
      image: gcr.io/projectsigstore/cosign:latest
      env:
        - name: COSIGN_PASSWORD
          valueFrom:
            secretKeyRef:
              name: cosign-keys
              key: password
      script: |
        # Sign image with key-based signing
        cosign sign --key k8s://default/cosign-keys \
          --tls-verify=false \
          --yes $(params.image)
        echo "✅ Image signed"

    - name: verify
      image: gcr.io/projectsigstore/cosign:latest
      script: |
        # Verify the signature
        cosign verify --key k8s://default/cosign-keys \
          --insecure-ignore-tlog \
          $(params.image)
        echo "✅ Signature verified"
```

**Note**: Key-based signing requires a `cosign-keys` secret containing the signing key. Generate with:
```bash
cosign generate-key-pair k8s://default/cosign-keys
```

### Tekton Task: Attach SBOM

```yaml
# tekton/tasks/attach-sbom.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: attach-sbom
spec:
  params:
    - name: image
  workspaces:
    - name: sbom
  steps:
    - name: attach
      image: gcr.io/projectsigstore/cosign:latest
      script: |
        # Attach SBOM to image in registry
        cosign attach sbom \
          --sbom $(workspaces.sbom.path)/sbom.json \
          $(params.image)
```

### Severity Thresholds

| Environment | Threshold | Action |
|-------------|-----------|--------|
| **Dev** | CRITICAL | Warn only |
| **Staging** | HIGH, CRITICAL | Fail pipeline |
| **Prod** | MEDIUM, HIGH, CRITICAL | Fail pipeline |

### Makefile Targets

```makefile
# Security Commands
scan:             # Scan current image with Trivy
scan-deps:        # Scan Python dependencies
sbom:             # Generate SBOM for current image
sign:             # Sign image with Cosign
verify:           # Verify image signature
security-report:  # Full security report (scan + sbom + vulns)
```

### Local Development

```bash
# Install tools locally for development
brew install trivy
brew install cosign

# Scan before pushing
make scan

# Generate SBOM
make sbom
```

## Consequences

### Positive
- Vulnerabilities caught before deployment
- Cryptographic proof of image integrity
- SBOM enables compliance and auditing
- Security mindset from day one
- Learn industry-standard supply chain security

### Negative
- Additional pipeline steps (~2-3 minutes added)
- Need to handle scan failures (not just ignore)
- Key-based signing requires secure key management (stored as K8s secret)
- Keyless signing would require OIDC provider (future enhancement)

### Neutral
- SBOM stored alongside images in registry
- Scan results need review process

## Future Enhancements

| Enhancement | Purpose |
|-------------|---------|
| **Kyverno/OPA** | Admission control - block unsigned images |
| **Dependency-Track** | SBOM management and monitoring |
| **Renovate** | Automated dependency updates |
| **In-toto** | Full attestation framework |

## References

- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [Cosign Documentation](https://docs.sigstore.dev/cosign/overview/)
- [SLSA Framework](https://slsa.dev/)
- [CycloneDX SBOM](https://cyclonedx.org/)
- [Sigstore](https://www.sigstore.dev/)
- [CISA SBOM Resources](https://www.cisa.gov/sbom)
