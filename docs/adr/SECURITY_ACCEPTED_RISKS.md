# Security Accepted Risks

This document tracks security vulnerabilities that are known and accepted with documented rationale.

## Document Information
- **Last Updated**: 2025-11-26
- **Review Cycle**: Monthly
- **Next Review**: 2025-12-26

---

## Accepted Vulnerabilities

### 1. libxslt - CVE-2025-7425 (HIGH)
**Status**: Accepted
**First Identified**: 2025-11-26
**Severity**: HIGH
**CVSS Score**: TBD

**Description**:
Heap use-after-free vulnerability in libxslt caused by atype corruption in xmlAttrPtr.

**Affected Packages**:
- `libxslt1-dev: 1.1.35-1.2+deb13u2`
- `libxslt1.1: 1.1.35-1.2+deb13u2`

**Fix Status**: No fix available from Debian
**Workaround**: None available

**Risk Assessment**:
- **Likelihood**: Low - requires specific XSLT processing patterns
- **Impact**: Medium - could affect lxml library operations
- **Overall Risk**: Low-Medium

**Mitigation**:
- Package is required for `lxml` and `readability-lxml` dependencies
- Input validation is performed before XSLT processing
- Monitor Debian security announcements for patches

**Acceptance Rationale**:
- Critical dependency for core functionality (article content extraction)
- No alternative packages available
- Risk is acceptable given low likelihood and input validation
- Will upgrade immediately when fix becomes available

**Review Actions**:
- [ ] Check Debian security tracker monthly
- [ ] Evaluate alternative base images (Alpine) if fix delayed >3 months
- [ ] Monitor application logs for XSLT-related errors

---

### 2. linux-libc-dev - Multiple Kernel CVEs (30 x HIGH)
**Status**: Accepted
**First Identified**: 2025-11-26
**Severity**: HIGH (multiple)

**Description**:
Multiple kernel vulnerabilities in linux-libc-dev package (kernel headers).

**Affected Packages**:
- `linux-libc-dev: 6.12.57-1`

**Fix Status**: No fixes available

**Risk Assessment**:
- **Likelihood**: Very Low - build-time only package
- **Impact**: None - not loaded at runtime
- **Overall Risk**: Very Low

**Mitigation**:
- Package is only used during build for compiling C extensions
- Not present in runtime attack surface
- Could be removed with multi-stage Docker builds

**Acceptance Rationale**:
- Build-time only dependency
- Zero runtime risk
- Not worth complexity of multi-stage builds for this risk level

**Review Actions**:
- [ ] Re-evaluate if moving to multi-stage builds
- [ ] Check if newer Debian releases have fixes

---

## Security Posture Summary

### Current State (v0.6.1)
- **CRITICAL vulnerabilities**: 0 ✅
- **HIGH vulnerabilities (accepted)**: 32
  - Runtime impact: 2 (libxslt)
  - Build-time only: 30 (kernel headers)
- **Application dependencies**: 0 vulnerabilities ✅

### CI/CD Configuration
- Trivy security scanning enabled
- **Fails on**: CRITICAL vulnerabilities
- **Reports on**: HIGH, MEDIUM, LOW vulnerabilities
- **Uploads to**: GitHub Security tab (SARIF)

### Security Improvements in v0.6.1
1. ✅ Upgraded `setuptools` from 65.5.1 → 80.9.0
   - Fixed CVE-2024-6345 (Remote code execution)
   - Fixed CVE-2025-47273 (Path traversal)
2. ✅ Re-enabled security scanning in CI/CD
3. ✅ Set CRITICAL severity as pipeline-blocking
4. ✅ Documented accepted risks

---

## Review Process

### Monthly Review Checklist
1. Re-scan current image with latest Trivy database
2. Check Debian security tracker for updates
3. Review new CVEs against accepted vulnerabilities
4. Update risk assessments if threat landscape changes
5. Verify mitigation measures are still effective
6. Update "Next Review" date

### Escalation Criteria
Immediately re-evaluate if:
- CVSS score increases above 8.0
- Active exploits are discovered in the wild
- New attack vectors are identified
- Debian releases emergency security update

---

## References

- [Trivy Documentation](https://trivy.dev/)
- [Debian Security Tracker](https://security-tracker.debian.org/)
- [CVE Database](https://cve.mitre.org/)
- [National Vulnerability Database](https://nvd.nist.gov/)

---

## Approval

**Accepted by**: Development Team
**Date**: 2025-11-26
**Issue**: #73 - Re-enable security scanning
