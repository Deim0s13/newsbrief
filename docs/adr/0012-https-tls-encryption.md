# ADR 0012: HTTPS/TLS Encryption

## Status

Accepted

## Date

2026-01-11

## Context

NewsBrief currently runs over HTTP (unencrypted), which presents security risks:

1. **Unencrypted traffic** - Data transmitted in plaintext
2. **No MITM protection** - Vulnerable to man-in-the-middle attacks
3. **Browser limitations** - Modern features (service workers, clipboard API) require HTTPS
4. **Security posture** - Required foundation before implementing authentication

We already use Caddy as our reverse proxy (ADR 0010), which has built-in automatic HTTPS support.

## Decision

Implement HTTPS using **Caddy's automatic TLS** for the **production (containerized) environment only**.

| Environment | Stack | URL | HTTPS |
|-------------|-------|-----|-------|
| **Development** | `make dev` → Python/uvicorn | `http://localhost:8787` | ❌ No |
| **Production** | `make deploy` → Podman + Caddy | `https://newsbrief.local` | ✅ Yes |

### Why No HTTPS in Development?

1. **Different architecture** - Dev runs uvicorn directly; prod runs through Caddy reverse proxy
2. **Complexity vs value** - Adding SSL to uvicorn requires separate certificate management, mkcert setup, and additional configuration for minimal security benefit
3. **Traffic stays local** - Dev traffic never leaves `localhost`, eliminating network interception risks
4. **Debugging simplicity** - Plain HTTP is easier to inspect with dev tools, curl, etc.
5. **Standard practice** - Most web frameworks (Django, Rails, Express) use HTTP for local dev

### Testing Implications

| Scenario | How to Test |
|----------|-------------|
| Feature development | Use `make dev` (HTTP) for fast iteration |
| HTTPS-specific features | Use `make deploy` (HTTPS) to test TLS behavior |
| Security headers | Must test in prod environment (Caddy adds headers) |
| Final integration | Always verify in prod environment before release |

### Accepted Risk

Features that behave differently over HTTPS (secure cookies, HSTS, service workers) must be explicitly tested in the production environment. This is an acceptable trade-off for development velocity.

### Future Consideration

If HTTPS becomes necessary in development (e.g., testing OAuth callbacks, PWA features), we can add optional uvicorn SSL support via:
- `mkcert` for local certificates
- `--ssl-keyfile` / `--ssl-certfile` flags to uvicorn

This would be a separate enhancement, not blocking current implementation.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Caddy automatic TLS** | Zero config for production, `tls internal` for local, automatic renewal | Requires trusting Caddy CA locally |
| **mkcert** | Well-known tool, trusted local certs | Extra tool to install, manual process |
| **Let's Encrypt only** | Real certificates | Doesn't work for `.local` domains |
| **nginx + certbot** | Industry standard | More complex, manual renewal setup |
| **Self-signed OpenSSL** | No dependencies | Browser warnings, manual renewal |

## Rationale

1. **Already using Caddy** - TLS is built-in, no additional tools needed
2. **`tls internal`** - Caddy generates a root CA and certificates automatically
3. **Consistent configuration** - Same Caddyfile for dev and prod (just swap `tls internal` for real domain)
4. **Automatic renewal** - No manual certificate management in production
5. **Security headers** - Caddy can add HSTS, X-Frame-Options, etc.

## Implementation

### Caddyfile Update

```
newsbrief.local {
    tls internal

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    reverse_proxy api:8787
}
```

### Trust Caddy CA on macOS

```bash
# Export Caddy's root certificate
podman exec newsbrief-caddy cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt

# Add to macOS Keychain
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain caddy-root.crt
```

### compose.yaml Updates

```yaml
caddy:
  image: caddy:2-alpine
  ports:
    - "80:80"
    - "443:443"  # Add HTTPS port
  volumes:
    - ./Caddyfile:/etc/caddy/Caddyfile:ro
    - caddy_data:/data      # Persist certificates
    - caddy_config:/config  # Persist config
```

### Uvicorn Proxy Headers

For FastAPI to generate correct `https://` URLs when behind Caddy, uvicorn must trust proxy headers:

```dockerfile
# Dockerfile CMD
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers", "--forwarded-allow-ips=*"]
```

- `--proxy-headers`: Enable trusting `X-Forwarded-Proto` header
- `--forwarded-allow-ips=*`: Trust headers from any IP (required for container networking where Caddy's IP varies)

Without this, `url_for()` generates `http://` URLs even when accessed via HTTPS, causing mixed content issues (Safari blocks HTTP resources on HTTPS pages).

### Production Configuration (Future)

For real domains with Let's Encrypt:

```
newsbrief.yourdomain.com {
    # No tls directive needed - Caddy auto-provisions via Let's Encrypt

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        # ... other headers
    }

    reverse_proxy api:8787
}
```

## Consequences

### Positive

- **Encrypted traffic** - All data protected in transit
- **Modern browser features** - Service workers, secure cookies, etc.
- **Security foundation** - Ready for authentication implementation
- **Simple management** - Caddy handles certificate lifecycle
- **HTTP→HTTPS redirect** - Caddy automatically redirects HTTP to HTTPS

### Negative

- **One-time CA trust** - Must add Caddy CA to macOS Keychain for local dev
- **Port 443** - Must be available (no conflicts with other HTTPS servers)
- **Slightly more complex setup** - Additional setup step for new developers

### Neutral

- **Performance** - TLS overhead is negligible on modern hardware
- **Debugging** - Can use `curl -k` or browser dev tools to inspect

## Security Considerations

1. **HSTS** - Forces browsers to always use HTTPS
2. **X-Frame-Options** - Prevents clickjacking
3. **X-Content-Type-Options** - Prevents MIME sniffing
4. **Referrer-Policy** - Controls referrer header leakage

## Migration Path

1. Update Caddyfile with `tls internal` and security headers
2. Add port 443 to compose.yaml
3. Add Caddy data volumes for certificate persistence
4. Document CA trust process for developers
5. Test HTTP→HTTPS redirect
6. Update documentation with HTTPS URLs

## Related

- ADR 0010: Caddy as Reverse Proxy
- Issue #34: Implement HTTPS/TLS encryption
- Future: Authentication implementation (requires HTTPS)
