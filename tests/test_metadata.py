from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_translation_are_valid_json():
    manifest = json.loads((ROOT / "custom_components/claude_usage/manifest.json").read_text())
    translation = json.loads((ROOT / "custom_components/claude_usage/translations/en.json").read_text())
    assert manifest["domain"] == "claude_usage"
    assert manifest["version"] == "0.1.0"
    assert translation["title"] == "Claude Usage"


def test_custom_component_does_not_ship_strings_json():
    assert not (ROOT / "custom_components/claude_usage/strings.json").exists()
