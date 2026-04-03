# Contributing to DataGov Analyst

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/agent-data-analyst.git`
3. Create a branch: `git checkout -b feature/your-feature-name`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and configure your credentials

## Development Setup

You'll need:
- Python 3.10+
- An OpenMetadata instance (or access to one)
- A PostgreSQL/Supabase database
- A Gemini API key or OpenRouter API key (free tier available)

## Making Changes

1. **One PR per feature/fix** — keep changes focused
2. **Reference an issue** — every PR should include `Closes #N`
3. **Write in English** — code, variables, functions, comments, commit messages
4. **Follow existing patterns** — look at how the codebase is structured before adding new files
5. **Test your changes** — run the agent and verify it works end-to-end

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add snowflake MCP connector
fix: handle null columns in distribution queries
docs: update architecture diagram
refactor: extract prompt templates to separate module
```

## Pull Request Process

1. Ensure your branch is up to date with `main`
2. Run the linter: `ruff check .`
3. Fill out the PR template
4. Wait for CI to pass
5. Request a review

## Adding a New MCP Connector

The architecture is plug & play. To add a new data source:

1. Create a new MCP server file (e.g., `snowflake_server.py`)
2. Implement the tools following the pattern in `sql_server.py`
3. Register it in `agent.py` with `register_mcp()`
4. Update `.env.example` with any new environment variables
5. Document in README.md

## Code of Conduct

Be respectful and constructive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Questions?

Open an issue with the `question` label or start a discussion.
