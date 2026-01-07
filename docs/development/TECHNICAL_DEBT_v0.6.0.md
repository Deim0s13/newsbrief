# Technical Debt for v0.6.0

**Date**: November 18, 2025
**Purpose**: Track technical debt items to address in the next milestone

---

## 🔒 Security

### 1. Re-enable Security Scanning
**Status**: Currently disabled with `continue-on-error: true`
**Location**: `.github/workflows/ci-cd.yml` - security-scan job
**Priority**: High

**Current State**:
```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  continue-on-error: true  # Don't fail pipeline on security scan issues
```

**Action Required**:
- Review Trivy scan results manually
- Fix any CRITICAL or HIGH vulnerabilities
- Remove `continue-on-error: true` once vulnerabilities are addressed
- Consider adding security scan to PR checks

**Why Disabled**: Was set to `continue-on-error` to prevent blocking deployments while we stabilized the v0.5.5 release.

---

## 📝 Code Quality

### 2. Mypy Type Annotations
**Status**: 30 type annotation warnings remaining
**Documentation**: `docs/MYPY_STATUS_v0.5.5.md`
**Priority**: Medium

**Current State**:
- Mypy runs with `--no-strict-optional` and `continue-on-error: true`
- All code is functionally correct
- Missing proper type hints in ~20 locations

**Action Required**:
- Fix Optional type annotations (3 errors)
- Add explicit type hints for SQL results (8 errors)
- Add missing required arguments (3 errors)
- Fix type incompatibilities (6 errors)
- Add proper type annotations for generators and collections (10 errors)

**Estimated Effort**: 2-3 hours

---

## 🧪 Testing

### 3. Expand Test Coverage
**Current Coverage**: ~60% (estimated, no coverage tool configured)
**Priority**: Medium

**Areas Needing Tests**:
- Story generation edge cases
- Scheduler functionality
- Feed health scoring algorithms
- OPML import/export edge cases
- Error handling paths

**Action Required**:
- Install `pytest-cov` for coverage reporting
- Add coverage reporting to CI/CD
- Target: 80% code coverage
- Focus on critical paths first (story generation, feed processing)

---

## 🔧 Refactoring

### 4. Clean Up Duplicate Code
**Status**: Some duplication still exists
**Priority**: Low

**Known Issues**:
- Multiple places with similar SQL query patterns
- Repeated validation logic
- Similar error handling blocks

**Action Required**:
- Extract common SQL query helpers
- Create shared validation utilities
- Standardize error handling patterns

---

## 📚 Documentation

### 5. API Documentation Completeness
**Status**: Basic documentation exists
**Priority**: Low

**Gaps**:
- Missing examples for scheduler configuration
- No troubleshooting guide
- Limited deployment documentation for production environments

**Action Required**:
- Add scheduler configuration examples with different timezones
- Create troubleshooting guide (common errors, solutions)
- Document production deployment best practices
- Add diagrams for story generation flow

---

## 🏗️ Infrastructure

### 6. Deployment Automation
**Status**: Deployments are simulated
**Priority**: Low (unless deploying to real infrastructure)

**Current State**:
```yaml
- name: Deploy to staging
  run: |
    echo "🎭 Deploying to staging environment"
```

**Action Required** (if real deployments needed):
- Configure actual Kubernetes cluster or VMs
- Set up kubectl or deployment tool
- Add deployment secrets to GitHub
- Configure health checks and rollback procedures
- Test deployment process end-to-end

---

## 📋 Milestone Planning

### For v0.6.0 - Enhanced Intelligence

**Must Have**:
- [ ] Re-enable security scanning (HIGH priority)
- [ ] Fix critical mypy type errors (MEDIUM priority)

**Nice to Have**:
- [ ] Improve test coverage to 80%
- [ ] Add coverage reporting to CI/CD
- [ ] Clean up code duplication

**Future**:
- [ ] Complete API documentation
- [ ] Production deployment automation (if needed)

---

## 🎯 Recommended Approach

### Week 1-2 of v0.6.0:
1. **Review security scan results** - Address any CRITICAL/HIGH issues
2. **Fix mypy type annotations** - Get to 0 errors with strict checking
3. **Set up coverage reporting** - Install pytest-cov, add to CI/CD

### During v0.6.0 feature development:
4. **Write tests for new features** - Maintain/improve coverage
5. **Refactor as needed** - Clean up duplication when working in those areas

### Before v0.6.0 release:
6. **Re-enable security scan** - Remove continue-on-error
7. **Update documentation** - Add missing sections

---

## 📊 Tracking

Create GitHub issues for each item:
- Issue #XX: Re-enable security scanning and address vulnerabilities
- Issue #XX: Fix remaining mypy type annotation warnings
- Issue #XX: Improve test coverage to 80%
- Issue #XX: Add deployment automation (if needed)

Label: `technical-debt`, `v0.6.0`

---

**Status**: Documented for tracking
**Next Review**: Start of v0.6.0 development
