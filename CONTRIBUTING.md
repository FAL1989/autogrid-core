# Contributing to AutoGrid

Thank you for your interest in contributing to AutoGrid! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/autogrid/autogrid/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)

### Suggesting Features

1. Check existing issues for similar suggestions
2. Create a new issue with the `enhancement` label
3. Describe the feature and its use case

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `make test`
5. Run linters: `make lint`
6. Commit with conventional commits
7. Push and create a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/autogrid.git
cd autogrid

# Install dependencies
make install

# Start development environment
make dev

# Run tests
make test
```

## Code Standards

### Python

- **Formatter**: Black (line length 88)
- **Import sorting**: isort
- **Linter**: flake8
- **Type checking**: mypy (strict mode)
- **Minimum coverage**: 80%

```bash
# Format code
make format

# Check linting
make lint
```

### TypeScript/JavaScript

- **Linter**: ESLint with Next.js config
- **Formatter**: Prettier (via ESLint)
- **Strict TypeScript**: enabled

```bash
cd web
npm run lint
npm run typecheck
```

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change without feature/fix
- `test`: Adding tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(bot): add grid strategy implementation
fix(api): handle invalid API key error
docs(readme): update installation instructions
test(strategies): add unit tests for DCA bot
```

## Project Structure

```
autogrid/
├── api/                 # FastAPI application
│   ├── routes/          # API endpoints
│   ├── models/          # Pydantic schemas
│   └── services/        # Business logic
├── bot/                 # Bot engine
│   ├── strategies/      # Trading strategies
│   └── exchange/        # Exchange connectors
├── web/                 # Next.js frontend
├── tests/               # Test suite
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
└── db/                  # Database migrations
```

## Testing

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# With coverage report
pytest --cov=api --cov=bot --cov-report=html
```

### Writing Tests

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Use pytest fixtures from `tests/conftest.py`
- Mock external services (exchanges, databases)

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add tests for new functionality
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested

## Security

- Never commit API keys or secrets
- Use `.env` for local configuration
- Report security vulnerabilities privately

## Questions?

Feel free to open an issue with the `question` label or reach out to the maintainers.

---

Thank you for contributing to AutoGrid!
