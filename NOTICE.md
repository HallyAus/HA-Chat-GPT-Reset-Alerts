# Attribution notice

This repository references and adapts implementation concepts from:

- `trickv/hass-claude-usage`
- Copyright (c) 2026 Patrick van Staveren
- MIT License

In particular, the Anthropic OAuth endpoints/client identifier, OAuth beta header, subscription usage endpoint and handling of the evolving `limits[]` / Extra Usage response schemas were validated against that project and current public Claude Code ecosystem behaviour.

The dual-provider architecture, Home Assistant reset tracking/event system, local Windows helper, security model and associated tests/documentation in this repository were created for this project.
