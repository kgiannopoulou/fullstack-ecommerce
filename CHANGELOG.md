# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- README: architecture diagram, design decisions, production considerations and limitations.
- MIT licence, `CONTRIBUTING.md` and this changelog.

## [1.0.0] - 2026-10-21

### Added
- 62-test Vitest + supertest suite against a real PostgreSQL: checkout races, deadlock-free locking,
  webhook replay and idempotency, the reservation sweeper, admin/webhook races, auth flows.
- Standard error body `{ error: { code, message, details, requestId } }` and Zod validation everywhere.
- Rate limits on auth and checkout.
- Email verification, password reset with hashed single-use tokens, and session revocation.
- `order_events` audit trail written in the same transaction as each change.
- Catalog search, filters, sorting and pagination; order history; verify/reset pages.
- Dockerfile, Render blueprint, API reference and CI (typecheck, tests, build, lint, Docker image).

## [0.2.0] - 2026-10-13

### Changed
- Stock is reserved atomically at checkout and order transitions are idempotent.

## [0.1.0] - 2026-09-13

### Added
- Next.js storefront and admin panel, Express/TypeScript API, PostgreSQL, JWT auth and Stripe Checkout.

[Unreleased]: https://github.com/kgiannopoulou/fullstack-ecommerce/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/kgiannopoulou/fullstack-ecommerce/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/kgiannopoulou/fullstack-ecommerce/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kgiannopoulou/fullstack-ecommerce/releases/tag/v0.1.0
