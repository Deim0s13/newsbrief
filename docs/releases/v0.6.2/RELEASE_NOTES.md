# v0.6.2 Release Notes - UI Polish & Fixes

**Release Date**: December 2025

## Overview

v0.6.2 focuses on UI polish, bug fixes, and infrastructure improvements following the v0.6.1 Enhanced Intelligence release. This release resolves 8 issues related to display, filtering, and developer experience.

## Key Changes

### 🎨 UI/UX Improvements

#### Local Tailwind CSS Build (Issue #80)
- **Changed**: Migrated from Tailwind CDN to local build for production-ready styling
- **Added**: `package.json`, `tailwind.config.js`, `postcss.config.js` for CSS toolchain
- **Added**: `npm run build:css` and `npm run watch:css` commands
- **Fixed**: Skim view toggle now works correctly with proper CSS specificity

#### Story Page Filters (Issue #81)
- **Added**: Topic filter dropdown on Stories page
- **Removed**: Time filter (deemed not valuable for story browsing)
- **Fixed**: Filter JavaScript now properly loads and functions
- **Fixed**: Conflict between `app.js` and `stories.js` resolved

#### Model/Status Display (Issue #82)
- **Fixed**: Story detail page now displays LLM model and status fields
- **Updated**: `StoryOut` Pydantic model includes `model` and `status` fields

### 🧹 Data Quality

#### HTML Sanitization (Issue #77)
- **Added**: `bleach` library for HTML sanitization
- **Added**: `sanitize_html()` function in `feeds.py`
- **Added**: Migration to sanitize existing article summaries
- **Fixed**: Raw HTML tags no longer appear in article summaries

#### Topic Classification (Issue #77)
- **Added**: Unified topic system in `app/topics.py`
- **Added**: Dynamic topic loading from `data/topics.json`
- **Added**: Two-step LLM classification (classify → normalize)
- **Added**: Auto-add capability for new topics
- **Fixed**: Articles now correctly classified (e.g., politics, ai-ml)

### 🤖 LLM Improvements

#### Default Model Upgrade
- **Changed**: Default model from `llama3.2:3b` to `llama3.1:8b`
- **Benefit**: Better topic classification accuracy
- **Benefit**: Improved story generation quality

### 📊 Other Fixes

#### Article Ranking (Issue #78)
- **Status**: Closed as "Working as Intended"
- **Finding**: Scores are correctly varied (0.1 to 7.0)
- **Created**: Epic #84 for future ranking improvements (v0.8.0)

#### Story Importance (Issue #79)
- **Fixed**: Old stories with artificially high scores now archive correctly
- **Finding**: Root cause was archiving scheduler not running

#### Feed Performance (Issue #83)
- **Status**: Closed as "Acceptable"
- **Created**: Issue #87 for scheduled automatic feed refresh

## New Issues Created

During v0.6.2 development, the following issues were created for future milestones:

| Issue | Description | Milestone |
|-------|-------------|-----------|
| #84 | Epic: Ranking & Personalization | v0.8.0 |
| #85 | Skim view for Stories page | Backlog |
| #86 | Epic: macOS Widget | Future |
| #87 | Scheduled feed refresh | v0.6.0 |

## Breaking Changes

None. All changes are backward compatible.

## Development Dependencies

New npm dependencies for local Tailwind build:
- `tailwindcss@^3.4.0`
- `postcss@^8.4.0`
- `postcss-cli@^11.0.0`
- `autoprefixer@^10.4.0`

New Python dependency:
- `bleach>=6.0.0`

## Upgrade Instructions

1. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Node dependencies** (for CSS development):
   ```bash
   npm install
   ```

3. **Build CSS** (if modifying styles):
   ```bash
   npm run build:css
   ```

4. **Restart application** to run migrations:
   ```bash
   uvicorn app.main:app --reload --port 8787
   ```

Migrations run automatically on startup:
- HTML sanitization of existing article summaries
- Topic reclassification of existing articles

## Contributors

- Development and testing completed with AI pair programming assistance

## Next Steps

- **v0.6.3**: Personalization features (user preferences, bookmarks)
- **v0.7.0**: LLM improvements (model evaluation, prompt engineering)
- **v0.8.0**: Ranking & Personalization epic
