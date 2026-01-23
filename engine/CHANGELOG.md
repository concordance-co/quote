# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Open source preparation: comprehensive documentation
- Root README.md with project overview and quick start guide
- CONTRIBUTING.md with contribution guidelines
- CODE_OF_CONDUCT.md (Contributor Covenant)
- SECURITY.md with security policy and vulnerability reporting
- Expanded .gitignore with comprehensive patterns

### Changed
- Replaced all `print()` statements with proper `logging` module calls
- Extracted `_extract_user_api_key()` helper function in local.py
- Updated inference/pyproject.toml with proper project description
- Added content to shared/README.md

### Removed
- Deleted backup files from `inference/src/quote/hot/backups/`
- Removed `.mods_registry.json` (local development artifact)
- Removed commented-out debug code from execute_impl.py
- Removed API key logging (security improvement)

### Security
- Fixed potential API key exposure in server logs

## [0.4.3] - 2025-01-15

### Added
- Initial public release
- Token-level intervention system for LLM generation
- Mod SDK for authoring generation interventions
- Events: Prefilled, ForwardPass, Sampled, Added
- Actions: ForceTokens, AdjustedLogits, Backtrack, ForceOutput, ToolCalls, AdjustedPrefill
- Flow Engine for multi-step constrained interactions
- OpenAI-compatible `/v1/chat/completions` API
- Hot-reloadable execution logic
- JSON Schema constrained generation example
- Backtracking with KV cache management
- Strategy system for constrained generation (Choices, Until, List, Chars)

### Infrastructure
- UV-based package management
- Workspace structure: inference, sdk, shared
- Integration with Modular MAX Engine
- Support for Modal deployment (remote inference)

[Unreleased]: https://github.com/concordance-co/concordance-v1/compare/v0.4.3...HEAD
[0.4.3]: https://github.com/concordance-co/concordance-v1/releases/tag/v0.4.3
