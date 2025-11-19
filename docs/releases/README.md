# Releases

Release documentation and version history for NewsBrief.

## 🚀 Version History

### v0.5.5 - Story-Based Aggregation (Current)
**Released**: November 18, 2025

Major release implementing the story-based aggregation architecture.

**Documentation**:
- [Release Notes](v0.5.5/RELEASE_v0.5.5.md) - Full release documentation
- [GitHub Release](v0.5.5/GITHUB_RELEASE_v0.5.5.md) - Release creation guide
- [Release Summary](v0.5.5/V0.5.5_FINAL_RELEASE_SUMMARY.md) - Final summary
- [Release Complete](v0.5.5/V0.5.5_RELEASE_COMPLETE.md) - Completion status
- [Cleanup Status](v0.5.5/V0.5.0_CLEANUP_STATUS.md) - Cleanup tracking
- [Cleanup Summary](v0.5.5/V0.5.0_CLEANUP_SUMMARY.md) - Cleanup details
- [Mypy Status](v0.5.5/MYPY_STATUS_v0.5.5.md) - Type checking status

**Key Features**:
- ✅ Story generation from clustered articles
- ✅ Multi-story synthesis with key points
- ✅ Story-first UI landing page
- ✅ Scheduled story generation (APScheduler)
- ✅ Automatic story archiving

**Technical Details**:
- Major architectural shift to story-centric model
- LLM-powered synthesis (Ollama/Llama 3.1)
- Semantic clustering with embeddings
- Background task scheduling
- Performance optimizations

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
4. Merge to `main` and tag release
5. Create GitHub Release with notes
6. Deploy to production

See [../development/BRANCHING_STRATEGY.md](../development/BRANCHING_STRATEGY.md) for details.

---

## 🔗 Quick Links

- **Latest Release**: [v0.5.5](v0.5.5/RELEASE_v0.5.5.md)
- **GitHub Releases**: [github.com/Deim0s13/newsbrief/releases](https://github.com/Deim0s13/newsbrief/releases)
- **Changelog**: See individual release notes

---

## 📚 Further Reading

- **Migration Guides**: See [../user-guide/](../user-guide/)
- **Technical Debt**: See [../development/TECHNICAL_DEBT_v0.6.0.md](../development/TECHNICAL_DEBT_v0.6.0.md)
- **Project Management**: See [../project-management/](../project-management/)

