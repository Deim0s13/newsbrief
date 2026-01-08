# ADR 0010: Caddy as Reverse Proxy

## Status

Accepted

## Date

2026-01-08

## Context

The production deployment needs a friendly local hostname (`newsbrief.local`) accessible on port 80, rather than requiring users to remember `localhost:8787`. This requires a reverse proxy to:

1. Listen on port 80
2. Forward requests to the API container on port 8787
3. Eventually support HTTPS/TLS (planned for security epic)

## Decision

Use **Caddy** as the reverse proxy, running as a container in the compose stack.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Caddy** | Simple declarative config, automatic HTTPS, lightweight Alpine image (~40MB), modern defaults | Newer, less community documentation than nginx |
| **nginx** | Industry standard, extensive documentation, very fast | More verbose config, manual certificate management |
| **Traefik** | Docker-native with auto-discovery, built-in dashboard | More complex for simple setups, heavier resource usage |
| **HAProxy** | Enterprise-grade, excellent performance | Overkill for single-app deployment, complex configuration |
| **macOS Apache** | Already installed on macOS | Not containerized, platform-specific, harder to maintain |

## Rationale

1. **Simplicity**: Caddy config is 4 lines vs 10+ for nginx
2. **Future-proof**: Built-in automatic HTTPS will simplify TLS implementation in security epic
3. **Containerized**: Consistent with our container-based architecture
4. **Lightweight**: Alpine-based image adds minimal overhead

## Implementation

```yaml
# compose.yaml
caddy:
  image: caddy:2-alpine
  ports:
    - "80:80"
  volumes:
    - ./Caddyfile:/etc/caddy/Caddyfile:ro
```

```
# Caddyfile
newsbrief.local {
    reverse_proxy api:8787
}
```

## Consequences

### Positive

- Simple, maintainable configuration
- Easy path to HTTPS when needed
- No additional software to install on host

### Negative

- Additional container in the stack
- Port 80 must be available (no other web servers running)

### Neutral

- Can be swapped for nginx/Traefik if needed without changing application code

## Related

- Issue #148: Configure friendly local hostname
- Future: Security epic for TLS/HTTPS implementation
