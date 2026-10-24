# Production security baseline for DroidFleet

This project is production-capable only when it is treated as a zero-trust control plane for managed devices, not as a lab-only remote control utility.

## Required defaults

- Only HTTPS is allowed for the server URL in production.
- HTTP is permitted only for `localhost`/loopback and only when `DROIDFLEET_ALLOW_INSECURE_LOOPBACK=true`.
- `ngrok` is disabled in a production profile.
- Agent credentials are hashed before persistence.
- Sensitive data is encrypted at rest; raw JSON secrets are no longer the default storage model.
- File transfer path is constrained to a safe root and denies path traversal.
- Secret-bearing text in logs is redacted before export.

## Minimum production profile

```env
DROIDFLEET_ENV=production
DROIDFLEET_SERVER=https://droidfleet.internal/api/agent/heartbeat
DROIDFLEET_ALLOW_INSECURE_LOOPBACK=false
DROIDFLEET_SECRET_KEY=<key-from-keyring-or-kms>
DROIDFLEET_FILE_ROOT=C:/ProgramData/DroidFleet/inbox
DROIDFLEET_MAX_FILE_SIZE_MB=50
DROIDFLEET_ALLOW_SHELL=false
```

## Hardening checklist

1. Enforce HTTPS-only URL validation.
2. Use mTLS or certificate-backed identity for FarmAgent.
3. Maintain per-agent enrollment and revocation.
4. Restrict shell execution to an allowlist.
5. Apply RBAC and device-scoped permissions.
6. Keep append-only audit logs with a clear correlation ID.
7. Sign and verify FarmAgent updates before execution.
8. Separate management traffic from general internet access using VPN or private network segmentation.
9. Store logs, screenshots, and device metadata with retention and encryption policies.
10. Run a 72-hour soak and 5–10 device load test before production rollout.

## What is explicitly forbidden

- On-by-default HTTP agent URLs.
- Shared credentials for all devices.
- Plain-text storage of agent tokens or account secrets.
- Arbitrary shell execution from untrusted input.
- Unverified update payloads or unsigned artifacts.
- Permanent public ngrok tunnels in the production profile.
