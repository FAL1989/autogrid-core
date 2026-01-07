# Changelog

All notable changes to AutoGrid Core are documented here.

## [v0.1.1] - 2026-01-07

### Added
- Unit tests for rate limiter client IP resolution.

### Changed
- Rate limiter uses proxy headers (`X-Forwarded-For`, `X-Real-IP`) before falling back
  to the direct client address.
