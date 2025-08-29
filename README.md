# bootServer

HTTP + minimal TFTP server for boot artifacts

## Overview

This project provides a combined HTTP and TFTP server designed for serving boot artifacts in network boot scenarios. It's particularly useful for PXE boot setups and CoreOS/Fedora CoreOS installations.

## Code Quality and Linting

This project maintains high code quality standards using multiple linting and formatting tools. All configuration is defined in the project's configuration files.

### Linting Tools Used

- **flake8**: Python style guide enforcement (PEP 8) and error detection
- **pyright**: Static type checker for Python with strict type checking enabled
- **black**: Uncompromising Python code formatter with 120 character line length
- **isort**: Import statement organizer, configured to work with black

### Available Make Commands

The project includes several make targets for code quality checks:

```bash
# Run all linting checks
make lint

# Run static type checking
make type-check

# Format code automatically
make format

# Check formatting without making changes
make format-check

# Run all quality checks (lint + type-check + format-check)
make quality

# Run tests
make test

# Setup development environment (installs gitleaks and enhanced git hooks)
make setup
```

### Configuration Files

#### `.flake8` and `setup.cfg`

- **Purpose**: Configures flake8 linting rules and mypy type checking
- **Line length**: 120 characters
- **Exclusions**: Standard build/cache directories
- **Special rules**: Relaxed documentation requirements for tests, allows unused imports in `__init__.py`

#### `pyproject.toml`

- **Purpose**: Modern Python project configuration including black, isort, pyright, and pytest settings
- **Black configuration**: 120 character line length, Python 3.13 target
- **isort configuration**: Black-compatible profile
- **Pyright configuration**: Strict type checking enabled with comprehensive error reporting
- **Pytest configuration**: Coverage reporting, strict markers, and test discovery settings

### Running Linting Locally

1. **Install dependencies** (if not already installed):

   ```bash
   pip install flake8 pyright black isort pytest pytest-cov
   ```

2. **Run individual tools**:

   ```bash
   # Lint code
   flake8 bootServer/ tests/

   # Type check
   pyright bootServer/ tests/

   # Format code
   black --line-length 120 .
   isort .

   # Check formatting
   black --check --line-length 120 .
   isort --check-only .
   ```

3. **Run all quality checks**:

   ```bash
   make quality
   ```

### Enhanced Pre-Commit Hooks

The project includes comprehensive pre-commit hooks that automatically run before each commit to ensure code quality and security. The hooks are set up via `make setup` and include:

#### What Gets Checked

- **🔍 flake8 linting**: PEP 8 compliance and error detection on staged Python files
- **🔍 pyright type checking**: Static type analysis across the entire project
- **🔍 Code formatting**: black and isort formatting validation
- **🔍 Security scanning**: gitleaks detection of potential secrets and credentials

#### Setup and Usage

1. **Initial setup** (run once):

   ```bash
   make setup
   ```

   This installs gitleaks and configures the enhanced pre-commit hooks.

2. **Normal development**: The hooks run automatically on `git commit`
   - ✅ All checks pass → commit proceeds
   - ❌ Any check fails → commit is blocked with helpful error messages

3. **Bypass hooks** (not recommended):

   ```bash
   git commit --no-verify
   ```

#### Alternative: pre-commit Framework

For teams preferring the standard pre-commit framework, a `.pre-commit-config.yaml` file is provided:

```bash
# Install pre-commit framework
pip install pre-commit

# Install the hooks
pre-commit install

# Run on all files (optional)
pre-commit run --all-files
```

### Development Workflow

1. **Setup environment** (first time):

   ```bash
   make setup  # Installs tools and configures enhanced pre-commit hooks
   ```

2. **Make your changes**

3. **Format code automatically**:

   ```bash
   make format
   ```

4. **Run quality checks**:

   ```bash
   make quality  # Runs all linting, type checking, and formatting checks
   ```

5. **Commit your changes**:

   ```bash
   git commit -m "your commit message"
   ```

   The enhanced pre-commit hook will automatically run all checks:
   - If all checks pass ✅, the commit proceeds
   - If any check fails ❌, you'll get specific error messages and the commit is blocked

6. **Push your changes**

The CI/CD pipeline will also run these same quality checks to ensure consistency.

#### Quick Fix Commands

If pre-commit checks fail, these commands can help:

- `make format` - Auto-fix formatting issues
- `make quality` - Run all checks locally before committing
- Check specific error messages for manual fixes needed

## Installation and Usage

```bash
# Install the package
pip install -e .

# Run the server
serve-boot-artifacts

# Or run tests
make test
```

## Project Structure

- `bootServer/`: Main application code
- `tests/`: Test suite
- `boot/`: Boot configuration files
- `scripts/`: Utility scripts
- `.github/`: GitHub Actions workflows
