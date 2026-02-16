# Source Credibility Research

**Issue**: #195 - Research and integrate source credibility data
**Date**: February 2026
**Status**: Complete

## Executive Summary

After evaluating available credibility data sources, **Media Bias/Fact Check (MBFC)** is recommended as the primary data source. A free community-maintained dataset provides immediate integration capability, with the option to upgrade to the official API for broader coverage and real-time updates.

## Data Sources Evaluated

### 1. Media Bias/Fact Check (MBFC) ⭐ Recommended

**Coverage**:
- MBFC API: "over 9,000 sources" (per MBFC official documentation)
- Community dataset: **2,068 domains** (measured 2026-02-16 from `drmikecrowe/mbfcext`)

**Data Fields Available**:
| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `domain` | string | `nytimes.com` | Key for matching |
| `name` | string | `The New York Times` | Display name |
| `bias` | string | `leftcenter` | Political leaning |
| `reporting` | string | `HIGH` | Factual accuracy |
| `url` | string | `https://mediabiasfactcheck.com/...` | MBFC review page |
| `homepage` | string | `http://www.nytimes.com/` | Source homepage |

**Bias Values**: `left`, `leftcenter`, `center`, `right-center`, `right`

**Reporting Values**: `VERY HIGH`, `HIGH`, `MOSTLY FACTUAL`, `MIXED`, `LOW`, `VERY LOW`, `FAKE`

**Special Categories**: `pro-science`, `satire`, `conspiracy`, `fake-news`

**Access Options**:
| Option | Cost | Requests | Coverage | Notes |
|--------|------|----------|----------|-------|
| Community JSON | Free | Unlimited | ~2,000 | May lag official DB |
| RapidAPI Pro | $10/mo | 100/mo | 9,000+ | Must link to MBFC |
| RapidAPI Ultra | $40/mo | 10K/mo | 9,000+ | Must link to MBFC |
| RapidAPI Mega | $200/mo | 100K/mo | 9,000+ | No attribution required |

### 2. AllSides

**Coverage**: 2,400+ sources

**Limitation**: Bias ratings only, no factual accuracy ratings. Would need licensing for systematic use.

### 3. Ad Fontes Media

**Coverage**: ~400 sources (focuses on major outlets)

**Limitation**: Smaller dataset, enterprise pricing for data access.

## Recommendation

### Phase 1: Community Dataset (Immediate)

Use MBFC community dataset from `drmikecrowe/mbfcext`:
- **URL**: `https://raw.githubusercontent.com/drmikecrowe/mbfcext/main/docs/sources.json`
- **Format**: JSON keyed by domain
- **Coverage**: 2,068 sources (logged at import)

### Phase 2: Official API (Future)

If broader coverage or real-time updates needed:
- Subscribe to MBFC RapidAPI ($10-40/mo)
- Provides 9,000+ sources
- Add attribution link per terms of service

---

## Data Model Design

### Schema

```sql
CREATE TABLE source_credibility (
    id SERIAL PRIMARY KEY,

    -- Core identification
    domain VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    homepage_url TEXT,

    -- Source classification (not a score penalty)
    source_type VARCHAR(20) NOT NULL DEFAULT 'news',
        -- 'news', 'satire', 'conspiracy', 'fake_news', 'state_media', 'advocacy', 'pro_science'

    -- Factual reporting (the ONLY input to credibility_score)
    factual_reporting VARCHAR(20),
        -- 'very_high', 'high', 'mostly_factual', 'mixed', 'low', 'very_low'

    -- Political bias (metadata only, NOT used in scoring)
    bias VARCHAR(20),
        -- 'left', 'left_center', 'center', 'right_center', 'right'

    -- Computed credibility score (0.0-1.0, based on factual_reporting only)
    credibility_score DECIMAL(3,2),

    -- Synthesis eligibility (satire/fake excluded by default)
    is_eligible_for_synthesis BOOLEAN DEFAULT TRUE,

    -- Provenance & versioning
    provider VARCHAR(50) NOT NULL DEFAULT 'mbfc_community',
        -- 'mbfc_community', 'mbfc_api', 'allsides', 'manual'
    provider_url TEXT,              -- MBFC review page URL
    dataset_version VARCHAR(100),   -- Git commit SHA or API version
    raw_payload JSONB,              -- Original data for troubleshooting

    -- Timestamps
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_source_credibility_domain ON source_credibility(domain);
CREATE INDEX idx_source_credibility_type ON source_credibility(source_type);
CREATE INDEX idx_source_credibility_score ON source_credibility(credibility_score);
```

### Credibility Score Calculation

**Principle**: Score is based ONLY on factual reporting accuracy, not political bias.

```python
# Factual reporting → credibility score (the ONLY factor)
FACTUAL_SCORES = {
    'very_high': 1.0,
    'high': 0.85,
    'mostly_factual': 0.7,
    'mixed': 0.5,
    'low': 0.3,
    'very_low': 0.15,
    # Special categories get None score, handled by source_type
}

def calculate_credibility_score(factual_reporting: str) -> float | None:
    """Calculate credibility score from factual reporting only."""
    if not factual_reporting:
        return None
    return FACTUAL_SCORES.get(factual_reporting.lower().replace(' ', '_'))
```

### Source Type Classification

Special MBFC categories map to `source_type` and `is_eligible_for_synthesis`:

| MBFC `bias` value | `source_type` | `is_eligible_for_synthesis` | Notes |
|-------------------|---------------|-----------------------------|----|
| `satire` | `satire` | `false` | Excluded from news synthesis |
| `conspiracy` | `conspiracy` | `false` | Excluded from synthesis |
| `fake-news` | `fake_news` | `false` | Excluded from synthesis |
| `pro-science` | `pro_science` | `true` | Science-focused, eligible |
| All others | `news` | `true` | Standard news source |

### Domain Canonicalization

Feed URLs need normalization before matching:

```python
import tldextract

def canonicalize_domain(url: str) -> str:
    """
    Extract canonical domain from URL for credibility matching.

    Handles:
    - www. prefix stripping
    - amp. prefix stripping
    - eTLD+1 extraction (bbc.co.uk → bbc.co.uk, not co.uk)
    - Known redirect domains
    """
    # Strip known prefixes
    STRIP_PREFIXES = ['www.', 'amp.', 'm.', 'mobile.']

    extracted = tldextract.extract(url)
    domain = f"{extracted.domain}.{extracted.suffix}"

    # Handle subdomains that are actually the brand
    if extracted.subdomain and extracted.subdomain not in ['www', 'amp', 'm', 'mobile']:
        # Check if subdomain is significant (e.g., news.bbc.co.uk)
        full_domain = f"{extracted.subdomain}.{domain}"
        # Could check against known subdomain brands

    return domain.lower()

# Exception cases requiring special handling:
DOMAIN_ALIASES = {
    'news.bbc.co.uk': 'bbc.co.uk',
    'bbc.com': 'bbc.co.uk',
    # Add known aliases as discovered
}
```

---

## Known Limitations

### MBFC-Specific

1. **US-centric bias framing**: Left/right spectrum based on US political context; less meaningful for international sources
2. **Single-source methodology**: MBFC ratings are editorial judgments, not crowd-sourced or algorithmic
3. **Lag in updates**: Community dataset may not reflect recent MBFC rating changes
4. **Missing sources**: Many regional/local news sources not rated

### Technical

1. **Domain matching imperfect**: Syndication, CDN domains, and URL shorteners may not match
2. **No per-article ratings**: Source-level only; individual articles may vary from source norm
3. **Section differences**: NYT news vs NYT opinion have different reliability profiles

### Editorial

1. **MBFC is widely used but not uncontroversial**: Treat as input signal, not truth oracle
2. **Transparency required**: Always show source of rating and link to methodology

---

## Operational Plan

### Import Process

1. Fetch `sources.json` from GitHub
2. Log import count and timestamp
3. Parse and normalize domains
4. Calculate credibility scores
5. Insert/update database records
6. Store raw payload for provenance

### Refresh Cadence

| Frequency | Action |
|-----------|--------|
| **Weekly** | Check for dataset updates (compare commit SHA) |
| **On change** | Generate diff report (added/removed/changed) |
| **Alert** | Notify if a tracked source's factual rating drops |

### Monitoring

- Track: import count, match rate vs feeds, sources with NULL scores
- Alert: sudden drops in source ratings, import failures
- Report: monthly credibility coverage statistics

---

## Product Integration Guidelines

### Hard Blocks (Rare)

Sources with `source_type` in (`fake_news`, `conspiracy`):
- Exclude from story clustering/synthesis by default
- May still display in article list with warning label

### Soft Weights (Common)

Sources with `credibility_score`:
- Weight in ranking and cluster selection
- Higher credibility sources given priority in synthesis

### Transparency (Always)

- Show credibility indicator next to source name
- Provide "Why this rating?" link to `provider_url` (MBFC page)
- Never hide that ratings come from external source

---

## Column Mapping: sources.json → Database

```python
def map_mbfc_to_record(domain: str, data: dict, dataset_version: str) -> dict:
    """Map MBFC sources.json entry to database record."""

    # Determine source_type from bias field
    bias = data.get('bias', '').lower()
    if bias == 'satire':
        source_type = 'satire'
        eligible = False
    elif bias == 'conspiracy':
        source_type = 'conspiracy'
        eligible = False
    elif bias == 'fake-news':
        source_type = 'fake_news'
        eligible = False
    elif bias == 'pro-science':
        source_type = 'pro_science'
        eligible = True
    else:
        source_type = 'news'
        eligible = True

    # Normalize bias for standard political spectrum
    political_bias = None
    if bias in ('left', 'leftcenter', 'center', 'right-center', 'right'):
        political_bias = bias.replace('-', '_')

    # Normalize factual reporting
    reporting = data.get('reporting')
    factual = reporting.lower().replace(' ', '_') if reporting else None

    return {
        'domain': domain.lower(),
        'name': data.get('name'),
        'homepage_url': data.get('homepage'),
        'source_type': source_type,
        'factual_reporting': factual,
        'bias': political_bias,
        'credibility_score': calculate_credibility_score(factual),
        'is_eligible_for_synthesis': eligible,
        'provider': 'mbfc_community',
        'provider_url': data.get('url'),
        'dataset_version': dataset_version,
        'raw_payload': data,
    }
```

---

## Multi-Signal Architecture (Long-term Vision)

MBFC is a **bootstrap signal**, not our identity. The architecture should support multiple credibility inputs:

### Phase 1: External Signal (v0.8.2)
- **MBFC** as primary source
- Quick to implement, broad coverage
- Provides immediate value

### Phase 2: NewsBrief-Native "Observed Quality" (Future)

Build internal quality signals from actual usage data:

| Signal | Description | Source |
|--------|-------------|--------|
| **Extraction success rate** | % of articles successfully parsed | Content pipeline |
| **Cluster consistency** | How often source articles cluster correctly | Deduplication engine |
| **Factual consistency** | Claim-source alignment checks | LLM verification |
| **User engagement** | Opens, hides, time-on-article | User behavior |
| **Correction rate** | How often source issues corrections | Manual tracking |

```sql
-- Future: observed_quality table
CREATE TABLE source_observed_quality (
    source_domain VARCHAR(255) PRIMARY KEY,
    extraction_success_rate DECIMAL(5,4),
    cluster_consistency_score DECIMAL(5,4),
    user_engagement_score DECIMAL(5,4),
    sample_size INTEGER,
    last_calculated TIMESTAMP
);
```

### Phase 3: Premium Provider Option (If Needed)

If stronger credibility footing required:
- **NewsGuard**: Most defensible, institutional credibility, paid
- **Ad Fontes Media**: Visual reliability chart, enterprise pricing

### Composite Score Design

```python
def calculate_composite_credibility(
    mbfc_score: float | None,
    observed_quality: float | None,
    premium_score: float | None,
    weights: dict = None
) -> float:
    """
    Combine multiple credibility signals.

    Default weights favor observed data when available,
    fall back to external ratings.
    """
    weights = weights or {
        'mbfc': 0.4,
        'observed': 0.5,
        'premium': 0.6,  # If premium overrides MBFC
    }

    signals = []
    if observed_quality is not None:
        signals.append((observed_quality, weights['observed']))
    if premium_score is not None:
        signals.append((premium_score, weights['premium']))
    elif mbfc_score is not None:
        signals.append((mbfc_score, weights['mbfc']))

    if not signals:
        return None

    total_weight = sum(w for _, w in signals)
    return sum(s * w for s, w in signals) / total_weight
```

---

## Next Steps

1. ✅ Research complete - MBFC selected as bootstrap signal
2. ⏳ Create database migration (#196)
3. ⏳ Implement import script with domain canonicalization
4. ⏳ Build UI indicators (#197)
5. ⏳ Integrate into synthesis weighting (#198)
6. 📋 Future: Add observed quality tracking (post-v0.8.2)

## References

- [MBFC Official Site](https://mediabiasfactcheck.com/)
- [MBFC Browser Extension Dataset](https://github.com/drmikecrowe/mbfcext)
- [MBFC RapidAPI](https://rapidapi.com/mbfcnews/api/media-bias-fact-check-ratings-api2)
- [ADR-0023: Intelligence Platform Strategy](../adr/0023-intelligence-platform-strategy.md)
- [tldextract - Python library for domain parsing](https://github.com/john-googledrive/tldextract)
