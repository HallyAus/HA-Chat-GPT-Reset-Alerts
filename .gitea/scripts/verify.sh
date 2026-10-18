#!/usr/bin/env bash
set -euo pipefail
test "$GITHUB_SERVER_URL" = 'http://192.168.1.130:3000'
test "$GITHUB_REPOSITORY" = 'hallyaus/HA-Chat-GPT-Reset-Alerts'
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
unset SOURCE_TOKEN GITEA_TOKEN GITHUB_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY
python -c 'import sys; assert sys.version_info[:2] == (3,13), "Use the original Python3.13 test toolchain"'
python -m pip install --disable-pip-version-check pytest==9.0.3 ruff==0.16.6
python -m ruff check custom_components tests
python -m pytest -q
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git diff --exit-code --
