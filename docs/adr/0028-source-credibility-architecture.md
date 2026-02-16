# ADR 0028: Source Credibility Architecture

## Status

**Accepted** - February 2026

## Context

NewsBrief aggregates content from multiple news sources, but currently treats all sources equally regardless of their factual accuracy or reliability. As outlined in ADR-0023 (Intelligence Platform Strategy), source credibility is a foundational capability for the intelligence platform vision.

### Problem Statement

1. **Quality variance**: Sources range from Pulitzer-winning journalism to known misinformation sites
2. **Synthesis integrity**: LLM synthesis treats a conspiracy blog equally to Reuters
3. **User trust**: Users can't assess source reliability without leaving the app
4. **Ranking quality**: High-credibility sources should surface more prominently

### Requirements

1. Source credibility must be **factual-accuracy based**, not politically biased
2. System must support **multiple data providers** (not locked to one)
3. Architecture must allow for **NewsBrief-native quality signals** over time
4. Implementation must be **transparent** (users can see why a source is rated)
5. Must handle **domain matching** robustly (www, subdomains, redirects)

## Decision

### Core Principle: Credibility ≠ Political Alignment

**Credibility score is based solely on factual reporting accuracy.** Political bias (left/right) is captured as metadata for transparency, but does NOT affect the credibility score.

This keeps the product:
- Defensible against accusations of political bias
- Useful across different political contexts
- Focused on what matters: factual accuracy

### Multi-Signal Architecture

MBFC is a **bootstrap signal**, not our identity. The architecture supports multiple credibility inputs:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CREDIBILITY SIGNALS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   External   │  │   Internal   │  │   Premium    │          │
│  │   (MBFC)     │  │  (Observed)  │  │  (Optional)  │          │
│  │              │  │              │  │              │          │
│  │ • Factual    │  │ • Extract    │  │ • NewsGuard  │          │
│  │   reporting  │  │   success    │  │ • Ad Fontes  │          │
│  │ • Bias label │  │ • Cluster    │  │              │          │
│  │ • Source     │  │   quality    │  │              │          │
│  │   type       │  │ • User       │  │              │          │
│  │              │  │   feedback   │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └────────────┬────┴─────────────────┘                   │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │   Composite   │                                  │
│              │   Credibility │                                  │
│              │     Score     │                                  │
│              └───────────────┘                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 1: External Signal (v0.8.2) - MBFC

**Provider**: Media Bias/Fact Check (MBFC)
- Coverage: ~2,000 sources (community dataset), 9,000+ (official API)
- Data: Factual reporting rating + political bias label
- Cost: Free (community) or $10-200/mo (API)

**Why MBFC**:
- Only widely-available dataset with both factual accuracy AND political bias
- Large coverage suitable for diverse feed sources
- Community dataset enables immediate implementation
- Clear upgrade path to official API if needed

**Why NOT others**:
- **AllSides**: Bias only, no factual accuracy ratings
- **Ad Fontes**: Small dataset (~400), enterprise pricing
- **NewsGuard**: Excellent but expensive, potential future addition

### Phase 2: Internal Signal (Future) - Observed Quality

Build NewsBrief-native quality signals from usage data:

| Signal | Description | Source |
|--------|-------------|--------|
| Extraction success rate | % of articles successfully parsed | Content pipeline |
| Cluster consistency | How often articles cluster correctly | Deduplication |
| User engagement | Opens, hides, time-on-article | User behavior |
| Correction rate | How often source issues corrections | Manual tracking |

### Phase 3: Premium Signal (If Needed)

If stronger credibility footing required:
- **NewsGuard**: Most defensible, institutional credibility
- **Ad Fontes**: Visual reliability chart, academic backing

### Source Type Classification

Special categories are handled as **source types**, not score penalties:

| Source Type | Synthesis Eligible | Notes |
|-------------|-------------------|-------|
| `news` | ✅ Yes | Standard news sources |
| `pro_science` | ✅ Yes | Science-focused outlets |
| `satire` | ❌ No | Excluded from synthesis |
| `conspiracy` | ❌ No | Excluded from synthesis |
| `fake_news` | ❌ No | Excluded, may show warning |
| `state_media` | ⚠️ Flagged | Included with label |
| `advocacy` | ⚠️ Flagged | Included with label |

### Domain Canonicalization

Feed URLs must be normalized before matching:

```python
# Canonical domain extraction
www.bbc.co.uk     → bbc.co.uk
amp.cnn.com       → cnn.com
m.reuters.com     → reuters.com
news.google.com   → (special case: extract actual source)
```

Implementation uses:
- `tldextract` for eTLD+1 extraction
- Known alias table for brand variations
- Subdomain rules for significant subdomains

### Credibility Score Calculation

```python
# Score based ONLY on factual reporting
FACTUAL_SCORES = {
    'very_high': 1.0,
    'high': 0.85,
    'mostly_factual': 0.70,
    'mixed': 0.50,
    'low': 0.30,
    'very_low': 0.15,
}

# Bias is metadata, NOT a score factor
# Left, right, center → stored but not penalized
```

## Schema Design

```sql
CREATE TABLE source_credibility (
    id SERIAL PRIMARY KEY,

    -- Core identification
    domain VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    homepage_url TEXT,

    -- Source classification (NOT a score penalty)
    source_type VARCHAR(20) NOT NULL DEFAULT 'news',

    -- Factual reporting (the ONLY input to credibility_score)
    factual_reporting VARCHAR(20),

    -- Political bias (metadata only, NOT used in scoring)
    bias VARCHAR(20),

    -- Computed credibility score (0.0-1.0)
    credibility_score DECIMAL(3,2),

    -- Synthesis eligibility
    is_eligible_for_synthesis BOOLEAN DEFAULT TRUE,

    -- Provenance & versioning
    provider VARCHAR(50) NOT NULL DEFAULT 'mbfc_community',
    provider_url TEXT,
    dataset_version VARCHAR(100),
    raw_payload JSONB,

    -- Timestamps
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_source_credibility_domain ON source_credibility(domain);
CREATE INDEX idx_source_credibility_type ON source_credibility(source_type);
CREATE INDEX idx_source_credibility_score ON source_credibility(credibility_score);
```

## Product Integration

### Hard Blocks (Rare)

Sources with `source_type` in (`fake_news`, `conspiracy`):
- Excluded from story clustering/synthesis by default
- May display in article list with warning label

### Soft Weights (Common)

Sources with `credibility_score`:
- Weighted in ranking (higher credibility → higher visibility)
- Weighted in synthesis (higher credibility sources cited first)
- Influences cluster selection for story grouping

### Transparency (Always)

- Show credibility indicator next to source name
- Provide "Why this rating?" link to provider URL
- Never hide that ratings come from external source
- Clearly label when source type is flagged (state_media, advocacy)

## Consequences

### Positive

1. **Factual focus**: Credibility based on accuracy, not ideology
2. **Extensible**: Multi-signal architecture allows future improvements
3. **Transparent**: Users can understand and verify ratings
4. **Defensible**: Clear separation of bias (metadata) vs credibility (factual)
5. **Practical**: Free dataset enables immediate implementation

### Negative

1. **External dependency**: Reliance on MBFC data quality and coverage
2. **US-centric**: MBFC bias framing is US political context
3. **Coverage gaps**: Many regional/local sources not rated
4. **Maintenance**: Periodic updates required to stay current

### Mitigations

1. **Multi-signal design**: Reduces dependency on any single provider
2. **Observed quality**: Internal signals reduce external dependency over time
3. **Graceful fallback**: Unrated sources get `NULL` score, not penalized
4. **Operational monitoring**: Track match rates, alert on coverage drops

## Known Limitations

1. **MBFC is not uncontroversial**: Widely used but methodology is proprietary
2. **Source-level only**: Individual articles may differ from source norm
3. **Section differences**: News vs opinion sections have different reliability
4. **Lag in updates**: Community dataset may not reflect recent changes
5. **International coverage**: Weaker outside US/UK/major English-language sources

## Operational Plan

| Frequency | Action |
|-----------|--------|
| Weekly | Check for dataset updates |
| On change | Generate diff report |
| Alert | Notify if tracked source rating drops |
| Monthly | Coverage statistics report |

## References

- [ADR-0023: Intelligence Platform Strategy](0023-intelligence-platform-strategy.md)
- [ADR-0006: Source Quality Weighting](0006-source-quality-weighting.md)
- [Source Credibility Research](../research/SOURCE-CREDIBILITY-RESEARCH.md)
- [MBFC Official Site](https://mediabiasfactcheck.com/)
- [MBFC Browser Extension Dataset](https://github.com/drmikecrowe/mbfcext)
