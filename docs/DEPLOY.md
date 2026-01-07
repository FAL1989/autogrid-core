# AutoGrid Core Deploy (Self-Hosted)

This repo ships the open-source core (API + bot engine + CLI). It does not
include the cloud dashboard or Telegram features. For cloud deploy, use the
private `AutoGrid` repository.

## 1) Environment Variables

Create a `.env` in the repo root:

```
ENCRYPTION_KEY=<openssl rand -hex 32>
JWT_SECRET=<openssl rand -hex 32>
POSTGRES_PASSWORD=<strong password>
```

Optional:
- `CORS_ORIGINS` for API access
- Exchange testnet flags (if used by your deployment)

## 2) Start the Stack

Development:

```bash
docker compose -f docker-compose.yml up -d --build
```

Production:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 3) Verify

```bash
curl -I http://localhost:8000
curl -I http://localhost:8000/docs
```

## 4) Release Governance

Use the core checklist and changelog to keep releases consistent:
- `CHANGELOG.md`
- `docs/RELEASE_CHECKLIST.md`

Tagging:
```bash
git tag -a vX.Y.Z -m "AutoGrid Core vX.Y.Z"
git push origin vX.Y.Z
```

If the cloud deploy consumes core images, publish new image tags and update the
cloud config to match.

## 5) Rollback

If deploy fails, checkout the previous commit/tag and re-run the compose up.
