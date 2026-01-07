# Release Checklist (AutoGrid Core)

Release: vX.Y.Z  
Date (UTC):  
Owner:  
Scope: Core only / Core + Cloud

## Pre-release
- [ ] `CHANGELOG.md` updated with this version.
- [ ] Tests run: `pytest tests/ -v` (record summary).
- [ ] `docs/DEPLOY.md` updated if procedures changed.

## Release
- [ ] Commit and push core changes.
- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "AutoGrid Core vX.Y.Z"`.
- [ ] Push tag: `git push origin vX.Y.Z`.
- [ ] If cloud consumes core images, build/publish:
  - `ghcr.io/<org>/autogrid-core-api:vX.Y.Z`
  - `ghcr.io/<org>/autogrid-core-bot:vX.Y.Z`
- [ ] Update cloud env or deploy config to new core image tags (if applicable).

## Post-release
- [ ] Record evidence in `docs/DEPLOY.md`.
- [ ] Verify API health: `GET /health` and `GET /api/v1/health`.
