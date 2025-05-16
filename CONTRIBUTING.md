# Contributing to GrimWaves API

Thank you for your interest in contributing to GrimWaves API! This document provides guidelines and instructions for contributing to this project.

## Development Setup

### Prerequisites

- Python 3.13+
- Docker and Docker Compose
- Poetry (Python dependency management)
- Git

### Local Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/grimwaves-api.git
   cd grimwaves-api
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Set up your local environment:
   ```bash
   cp .env.example .env
   # Edit .env file with your settings
   ```

4. Add local domain entries to your hosts file:
   ```
   127.0.0.1 api.grimwaves.local
   127.0.0.1 traefik.grimwaves.local
   127.0.0.1 grimwaves.local
   ```

5. Generate development certificates:
   ```bash
   make certs
   ```

6. Start the development environment:
   ```bash
   make dev
   ```

## Code Style and Guidelines

- We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Type annotations are required for all function definitions
- We follow PEP 8 with 88 character line length (Black compatible)

Run linting before submitting a PR:
```bash
poetry run ruff check .
poetry run ruff format .
```

## Creating Pull Requests

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes, following our code style guidelines.

3. Write tests for your changes.

4. Run tests to ensure everything works:
   ```bash
   poetry run pytest
   ```

5. Commit your changes using conventional commit format:
   ```bash
   git commit -m "feat: add new feature"
   git commit -m "fix: resolve bug in API"
   ```

6. Push your changes to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

7. Create a pull request to the `main` branch of the original repository.

## Commit Message Guidelines

We follow the conventional commits specification:

- `feat`: A new feature
- `fix`: A bug fix
- `improve`: Improvements to existing functionality
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: Code changes that neither fix a bug nor add a feature
- `test`: Adding or modifying tests
- `ci`: Changes to CI configuration
- `build`: Changes affecting the build system or dependencies
- `perf`: Performance improvements
- `chore`: Other changes that don't modify source or test files

Example:
```
feat: add support for downloading release metadata
```

## Release Process

Releases are managed by the maintainers. We use semantic versioning:

- MAJOR version for incompatible API changes
- MINOR version for functionality added in a backward compatible manner
- PATCH version for backward compatible bug fixes

## License

By contributing to this project, you agree that your contributions will be licensed under the project's license.

## Questions?

If you have any questions about contributing, please open an issue or contact the maintainers. 