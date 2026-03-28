# Contributing

Thanks for your interest in contributing to Trader!

## Getting started

1. Fork the repo and clone your fork
2. Install dependencies: `uv sync --extra dev`
3. Create a feature branch: `git checkout -b feature/my-change`
4. Make your changes
5. Run tests: `make test`
6. Commit using [Conventional Commits](https://www.conventionalcommits.org/) (see below)
7. Push and open a PR against `main`

## Conventional Commits

This project uses conventional commits for automatic versioning and changelog generation. Prefix your commit messages:

| Prefix | When to use | Version bump |
|--------|-------------|--------------|
| `feat:` | New feature | minor |
| `fix:` | Bug fix | patch |
| `docs:` | Documentation only | none |
| `chore:` | Maintenance, deps, CI | none |
| `test:` | Adding/updating tests | none |
| `refactor:` | Code change that neither fixes a bug nor adds a feature | none |
| `BREAKING CHANGE:` | In commit body, or `feat!:` / `fix!:` | major |

Examples:
```
feat: add trailing stop order type
fix: correct EU scanner location codes
feat!: redesign adapter interface
```

## Development setup

### IBKR Gateway

You need an IBKR account (paper is fine) and the Client Portal Gateway running. See the [README](README.md#quick-start) for setup instructions.

### Running tests

```bash
make test                    # all tests
uv run python -m pytest tests/unit/ -v   # unit only
```

> Always use `uv run python -m pytest`, never bare `pytest`.

### Code style

- Type hints on public functions
- All CLI output must be valid JSON
- New broker operations go through the adapter interface (`trader/adapters/base.py`)
- Strategies are pure functions in `trader/strategies/`

## Pull requests

- PRs require 1 approving review before merge
- Keep PRs focused — one feature or fix per PR
- Include tests for new functionality
- Update the README if you change CLI commands or setup steps

## Reporting issues

Open an issue with:
- What you expected
- What happened instead
- Steps to reproduce
- `uv run trader --version` output
