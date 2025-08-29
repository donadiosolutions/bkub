# Makefile for running tests
.PHONY: test
test:
	pytest -q

.PHONY: setup
setup: setup-gitleaks

setup-gitleaks:
	@echo "Setting up gitleaks and Git hook locally"
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
	@# Create a .githooks directory and a pre-commit hook that runs gitleaks
	mkdir -p .githooks
	@printf '%s\n' '#!/usr/bin/env sh' \
	'# Pre-commit hook: run gitleaks in detect mode on staged files; exit non-zero to block commit on findings.' \
	'echo "Running gitleaks pre-commit scan..."' \
	'# Run a quick scan of all staged files (if none, scan repo)' \
	'STAGED="$$(git diff --cached --name-only --diff-filter=ACMRTUXB)"' \
	'if [ -n "$$STAGED" ]; then' \
	'	git --no-pager diff --name-only --cached | xargs -r gitleaks detect --source -' \
	'	RC=$$?' \
	'else' \
	'	gitleaks detect --source . --config .gitleaks.toml --redact' \
	'	RC=$$?' \
	'fi' \
	'if [ $$RC -ne 0 ]; then' \
	'	echo "gitleaks detected potential secrets. Please resolve or add allowlist entries before committing."' \
	'	exit $$RC' \
	'fi' \
	'exit 0' > .githooks/pre-commit && chmod +x .githooks/pre-commit
	git config core.hooksPath .githooks
	@echo "Configured git to use .githooks and created pre-commit hook to run gitleaks"
	@echo "Setup complete: gitleaks and Git pre-commit hook configured"
