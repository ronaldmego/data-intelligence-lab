# Contributing to OpenMetadata Agent

Thanks for your interest in contributing! This project is open to contributions of all kinds: bug reports, feature requests, documentation improvements, and code.

## How to contribute

### Reporting bugs

1. Check [existing issues](https://github.com/ronaldmego/openmetadata-mcp-agent/issues) to avoid duplicates
2. Open a new issue with:
   - What you expected to happen
   - What actually happened
   - Steps to reproduce
   - Your environment (Python version, OS, OpenMetadata version)

### Suggesting features

Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### Submitting code

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Test against a running OpenMetadata instance
5. Commit with a descriptive message: `git commit -m "feat: add new tool for ..."`
6. Push to your fork and open a Pull Request

### Commit message format

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `chore:` — maintenance tasks

## Development setup

```bash
git clone https://github.com/ronaldmego/openmetadata-mcp-agent.git
cd openmetadata-mcp-agent
pip install -r requirements.txt
cp .env.example .env
# Fill in your credentials
```

You need a running OpenMetadata instance to test. See the [README](./README.md) for details.

## Code style

- Python 3.10+
- Code, variables, and comments in English
- Keep functions focused and well-named

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
