# Makefile for running tests
.PHONY: test setup lint type-check format format-check quality

test:
	pytest -q

setup: setup-gitleaks

# Code quality targets
lint:
	flake8 bootServer/ tests/

type-check:
	pyright bootServer/ tests/

format:
	black --line-length 120 .
	isort .

format-check:
	black --check --line-length 120 .
	isort --check-only .

quality: lint type-check format-check
	@echo "All quality checks passed!"

setup-gitleaks:
	@echo "Setting up gitleaks and enhanced Git pre-commit hooks locally"
	@set -e; \
	# If gitleaks already available, skip installation; otherwise attempt to install
	if command -v gitleaks >/dev/null 2>&1; then \
		echo "gitleaks already installed; skipping installation"; \
	else \
		# Try Homebrew on macOS first; then detect common Linux package managers (apt, dnf, pacman, apk) \
		if command -v brew >/dev/null 2>&1; then \
			echo "Installing gitleaks via brew"; \
			brew install gitleaks || true; \
		elif [ "$$(uname -s)" = "Darwin" ]; then \
			echo "Homebrew not found on macOS — please install Homebrew or gitleaks manually"; \
			exit 1; \
		else \
			# Linux: detect package manager \
			if command -v apt-get >/dev/null 2>&1; then \
				echo "Detected apt-get: attempting apt-get install gitleaks"; \
				sudo apt-get update && sudo apt-get install -y gitleaks || true; \
			elif command -v dnf >/dev/null 2>&1; then \
				echo "Detected dnf: attempting dnf install gitleaks"; \
				sudo dnf install -y gitleaks || true; \
			elif command -v pacman >/dev/null 2>&1; then \
				echo "Detected pacman: attempting pacman -S gitleaks"; \
				sudo pacman -Sy --noconfirm gitleaks || true; \
			elif command -v apk >/dev/null 2>&1; then \
				echo "Detected apk: attempting apk add gitleaks"; \
				sudo apk add --no-cache gitleaks || true; \
			else \
				echo "No known package manager found or gitleaks package unavailable; will attempt to download the release binary"; \
			fi; \
			# If gitleaks still missing, fallback to release binary download \
			if ! command -v gitleaks >/dev/null 2>&1; then \
				echo "Downloading gitleaks release binary as fallback"; \
				ARCH="$$(uname -m)"; \
				if [ "$$ARCH" = "x86_64" ] || [ "$$ARCH" = "amd64" ]; then \
					URL=https://github.com/zricethezav/gitleaks/releases/latest/download/gitleaks-linux-amd64; \
				elif echo "$$ARCH" | grep -qi arm; then \
					URL=https://github.com/zricethezav/gitleaks/releases/latest/download/gitleaks-linux-arm64; \
				else \
					URL=https://github.com/zricethezav/gitleaks/releases/latest/download/gitleaks-linux-amd64; \
				fi; \
				curl -sL "$$URL" -o /tmp/gitleaks.tmp || true; \
				if [ -f /tmp/gitleaks.tmp ]; then \
					sudo mv /tmp/gitleaks.tmp /usr/local/bin/gitleaks; sudo chmod +x /usr/local/bin/gitleaks; \
				else \
					echo "Failed to download gitleaks binary automatically. Please install gitleaks manually and ensure it's on PATH."; \
				fi; \
			fi; \
		fi; \
	fi
	@# Ensure gitleaks is on PATH
	@command -v gitleaks >/dev/null 2>&1 || (echo "gitleaks not found on PATH after install" && exit 1)
	@# Check for required tools
	@echo "Checking for required development tools..."
	@command -v flake8 >/dev/null 2>&1 || (echo "⚠️  flake8 not found. Install with: pip install flake8" && exit 1)
	@command -v pyright >/dev/null 2>&1 || (echo "⚠️  pyright not found. Install with: pip install pyright" && exit 1)
	@command -v black >/dev/null 2>&1 || (echo "⚠️  black not found. Install with: pip install black" && exit 1)
	@command -v isort >/dev/null 2>&1 || (echo "⚠️  isort not found. Install with: pip install isort" && exit 1)
	@echo "✅ All required tools found"
	@# Create .githooks directory and ensure the enhanced pre-commit hook is executable
	mkdir -p .githooks
	chmod +x .githooks/pre-commit
	git config core.hooksPath .githooks
	@echo "✅ Configured git to use .githooks with enhanced pre-commit hook"
	@echo "📋 Enhanced pre-commit hook includes:"
	@echo "   • flake8 linting"
	@echo "   • pyright type checking"
	@echo "   • black/isort formatting checks"
	@echo "   • gitleaks security scanning"
	@echo "🎉 Setup complete: Enhanced pre-commit hooks configured"
	@echo ""
	@echo "💡 To install development dependencies if missing:"
	@echo "   pip install flake8 pyright black isort pytest pytest-cov"
