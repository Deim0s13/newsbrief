# Releases

Release documentation and version history for NewsBrief.

## 🚀 Version History

### v0.7.3 - Operations & Observability (Current)
**Released**: January 2026

Enhanced observability and developer experience improvements.

**Key Changes**:
- 📊 **Structured Logging**: JSON logs in production, human-readable in development (ADR-0011)
- 🏥 **Health Endpoints**: Kubernetes-style `/healthz`, `/readyz`, `/ollamaz` probes
- 🎨 **Feed Management UI**: Fixed legibility issues with proper column widths
- 🏷️ **Dev/Prod Separation**: Visual DEV banner and browser tab prefix in development
- 🔧 **Route Fix**: Resolved 422 errors on `/feeds/categories` endpoint
- ⏱️ **Timing Instrumentation**: Duration logging for key operations

---

### v0.7.2 - Container & Deployment
**Released**: January 2026

Production-ready containerization and deployment automation.

**Key Changes**:
- 🐳 **Multi-stage Dockerfile**: Optimized build with non-root user
- 🏥 **Health Endpoint**: `/health` with database, LLM, scheduler status
- 🚀 **Production Deployment**: `make deploy`, `deploy-stop`, `deploy-status`
- 💾 **Database Backup/Restore**: `make db-backup`, `db-restore`
- 🌐 **Caddy Reverse Proxy**: Access at `http://newsbrief.local`
- ⚡ **Auto-start on Login**: launchd plist with `make autostart-install`
- 🔒 **CI/CD Stabilization**: Pre-commit hooks, locked Action versions

---

### v0.7.1 - PostgreSQL Migration
**Released**: January 2026

Production database migration to PostgreSQL.

**Key Changes**:
- 🐘 **PostgreSQL Support**: Production-ready database via DATABASE_URL
- 🔀 **Dual Database Mode**: SQLite for dev, PostgreSQL for production
- 📦 **ORM Models**: Central `orm_models.py` with portable schema
- 🔄 **Alembic Migrations**: Schema versioning and migration tooling
- 🛠️ **Database Commands**: `make db-up`, `db-down`, `db-psql`, `db-reset`

---

### v0.6.5 - Personalization
**Released**: January 2026

Personalized content ranking based on user preferences.

**Key Changes**:
- ⭐ **Interest-Based Ranking**: Topic weights for personalized ordering
- 📊 **Source Quality Weighting**: Feed/domain reputation in scoring
- 🏥 **Feed Health Improvements**: Response time tracking
- ⚙️ **Configurable Blending**: 50% importance + 30% interest + 20% source
- 🔘 **Personalization Toggle**: Enable/disable in UI

**Issues Resolved**: #57, #58, #71

---

### v0.6.4 - Code Quality
**Released**: January 2026

Type safety and test coverage improvements.

**Key Changes**:
- ✅ **Type Safety**: mypy passes with 0 errors in 13 source files
- 🧪 **Test Coverage**: Improved 30% → 41% with 192 tests
- 📝 **Ranking Tests**: Comprehensive tests for recency, keywords, topics
- 🔄 **CI/CD Improvements**: pytest-cov integration

**Issues Resolved**: #22, #74, #75

---

### v0.6.3 - Performance
**Released**: January 2026

Performance optimizations and API enhancements.

**Key Changes**:
- 🗄️ **Synthesis Caching**: LLM results cached with TTL and invalidation
- 🔄 **Incremental Updates**: Story versioning with overlap detection
- 🔍 **API Enhancements**: 6 new filters on `/items` endpoint
- ⏰ **Scheduled Refresh**: Automatic feed refresh at 5:30 AM

**Issues Resolved**: #46, #49, #56, #87

---

### v0.6.2 - UI Polish & Fixes
**Released**: December 2025

UI polish, bug fixes, and infrastructure improvements.

**Documentation**: [Release Notes](v0.6.2/RELEASE_NOTES.md)

**Key Changes**:
- 🎨 **Local Tailwind CSS**: Production-ready styling
- 🧹 **HTML Sanitization**: Clean article summaries with `bleach`
- 🏷️ **Topic Classification**: Unified system with LLM
- 🔍 **Topic Filter**: On Stories page
- 📊 **Model/Status Display**: On story detail page
- 🤖 **Default LLM Upgrade**: `llama3.1:8b`

**Issues Resolved**: #77, #78, #79, #80, #81, #82, #83

---

### v0.6.1 - Enhanced Intelligence
**Released**: December 2025

Enhanced clustering and story quality scoring.

**Documentation**: [Release Notes](v0.6.1/RELEASE_NOTES.md)

**Key Features**:
- 🧠 **Entity Extraction**: Companies, products, people, technologies
- 🔗 **Semantic Similarity**: Entity overlap and bigrams/trigrams
- ⭐ **Story Quality Scoring**: Importance, freshness, quality
- 💬 **UX Improvements**: Detailed feedback messages
- 👁️ **Skim/Detail Toggle**: Flexible viewing modes

**Issues Resolved**: #40, #41, #43, #67, #70, #76

---

### v0.5.5 - Story-Based Aggregation
**Released**: November 18, 2025

Major release implementing story-based aggregation architecture.

**Documentation**:
- [Release Notes](v0.5.5/RELEASE_v0.5.5.md)
- [GitHub Release](v0.5.5/GITHUB_RELEASE_v0.5.5.md)
- [Release Summary](v0.5.5/V0.5.5_FINAL_RELEASE_SUMMARY.md)

**Key Features**:
- ✅ Story generation from clustered articles
- ✅ Multi-story synthesis with key points
- ✅ Story-first UI landing page
- ✅ Scheduled story generation (APScheduler)
- ✅ Automatic story archiving

---

## 📦 Release Process

### Semantic Versioning
NewsBrief follows [Semantic Versioning](https://semver.org/):
- **Major** (x.0.0): Breaking changes
- **Minor** (0.x.0): New features, backward compatible
- **Patch** (0.0.x): Bug fixes, backward compatible

### Release Workflow
1. Feature development on `feature/*` branches
2. Merge to `dev` branch for integration
3. Testing and validation
4. Update documentation (README, releases)
5. Merge to `main` and tag release
6. Create GitHub Release with notes
7. Deploy to production

### Release Checklist
- [ ] All issues in milestone closed
- [ ] CI/CD pipeline passing
- [ ] README updated with version changes
- [ ] This releases README updated
- [ ] ADRs created for architectural decisions
- [ ] Manual testing completed
- [ ] Release tagged and published

---

## 🔗 Quick Links

- **Latest Release**: v0.7.3 (Operations & Observability)
- **GitHub Releases**: [github.com/Deim0s13/newsbrief/releases](https://github.com/Deim0s13/newsbrief/releases)
- **Project Board**: [github.com/Deim0s13/newsbrief/projects](https://github.com/orgs/Deim0s13/projects)
- **Milestones**: [github.com/Deim0s13/newsbrief/milestones](https://github.com/Deim0s13/newsbrief/milestones)

---

## 📚 Further Reading

- **Architecture Decisions**: See [../adr/](../adr/)
- **Development Guide**: See [../development/](../development/)
- **Project Management**: See [../project-management/](../project-management/)
