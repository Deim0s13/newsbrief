# ADR 0014: API Rate Limiting

## Status

Accepted

## Date

2026-01-11

## Context

The NewsBrief API needs protection against abuse, whether accidental (runaway scripts) or intentional (DoS attempts). Rate limiting provides:

1. **Stability** - Prevents single clients from overwhelming the server
2. **Fair usage** - Ensures resources are shared among all users
3. **Cost control** - Limits LLM API calls (expensive operations)
4. **Security** - Mitigates brute-force and scraping attacks

## Decision

Implement rate limiting using **slowapi** with in-memory storage, configurable via environment variables.

| Aspect | Decision |
|--------|----------|
| **Library** | slowapi (FastAPI extension) |
| **Storage** | In-memory (default), Redis-ready |
| **Key** | Client IP address |
| **Scope** | Global default + per-endpoint overrides |

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **slowapi** ✅ | Simple, no dependencies, FastAPI native, X-RateLimit headers | In-memory doesn't scale horizontally |
| **fastapi-limiter** | Redis-native, distributed | Requires Redis even for single instance |
| **Custom middleware** | Full control | More code to maintain, reinventing wheel |
| **Nginx/Caddy rate limiting** | Offloads from app | Less granular, can't limit by endpoint type |

## Rationale

1. **No new infrastructure** - In-memory storage works for single-instance deployment
2. **Future-ready** - slowapi supports Redis backend when scaling needed
3. **Standard headers** - Automatic X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
4. **Per-endpoint flexibility** - Different limits for expensive operations (LLM) vs cheap ones (health checks)

## Implementation

### Rate Limit Configuration

```python
# Environment variables
RATE_LIMIT_DEFAULT = "100/minute"      # General API endpoints
RATE_LIMIT_LLM = "10/minute"           # LLM-intensive operations (story generation)
RATE_LIMIT_AUTH = "5/minute"           # Future: login attempts
```

### Endpoint Categories

| Category | Default Limit | Endpoints |
|----------|---------------|-----------|
| **Standard** | 100/min | GET endpoints, feeds, articles |
| **LLM-intensive** | 10/min | POST /stories/generate, POST /refresh |
| **Health** | Unlimited | /health, /healthz, /readyz |

### Code Structure

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/feeds")
@limiter.limit("100/minute")
async def get_feeds(request: Request):
    ...

@app.post("/stories/generate")
@limiter.limit("10/minute")
async def generate_stories(request: Request):
    ...
```

### Response Headers

All rate-limited responses include:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Timestamp when limit resets

### 429 Response

```json
{
  "error": "Rate limit exceeded",
  "detail": "10 per 1 minute",
  "retry_after": 45
}
```

## Consequences

### Positive

- Protection against abuse without infrastructure changes
- Standard rate limit headers for client awareness
- Granular control per endpoint
- Easy upgrade path to Redis for scaling

### Negative

- In-memory limits reset on server restart
- Not suitable for horizontal scaling without Redis
- Adds small overhead to each request

### Neutral

- Health endpoints excluded (always available for monitoring)
- Rate limits apply per IP (shared IPs may hit limits together)

## Future Enhancements

1. **Redis backend** - For distributed deployments
2. **API key-based limits** - Higher limits for authenticated users
3. **Adaptive limits** - Adjust based on server load
4. **Endpoint-specific overrides** - Configure via admin UI

## Related

- Issue #124: Implement API rate limiting
- Future: #122 User authentication (for per-user limits)
- ADR 0012: HTTPS/TLS (rate limiting works with secure connections)
