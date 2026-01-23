# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-23

### Added
- Initial open source release
- Real-time log streaming via WebSocket
- Token sequence visualization with probability distributions
- Trace tree analysis with step-by-step execution views
- Metrics dashboard for latency, throughput, and token statistics
- Interactive Playground for running inference experiments
- Collections feature for organizing related requests
- Public sharing for individual requests and collections
- Discussion/comment system for collaboration
- Favorites system for bookmarking requests
- API key authentication
- Multi-user support with admin and non-admin roles
- Filter logs by collection, API key, or model
- Responsive design for various screen sizes

### Documentation
- Added comprehensive README.md
- Added CONTRIBUTING.md with contribution guidelines
- Added MIT LICENSE
- Created env.example for environment configuration
- Added .gitignore for proper file exclusion

### Security
- Removed test data files from repository
- Added environment variable support for sensitive configuration
- Implemented conditional debug logging (disabled in production)

## [Unreleased]

### Planned
- Testing framework integration (Vitest)
- ESLint and Prettier configuration
- GitHub Actions CI/CD pipeline
- Accessibility improvements
- Additional API documentation

---

[1.0.0]: https://github.com/concordance-co/concordance/releases/tag/v1.0.0
[Unreleased]: https://github.com/concordance-co/concordance/compare/v1.0.0...HEAD
