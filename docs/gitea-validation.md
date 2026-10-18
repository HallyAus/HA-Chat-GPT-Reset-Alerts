# Personal source validation

The Gitea workflow uses the separate personal runner with the original
Python3.13 lint and complete parsing/reset/privacy tests, followed by the
pinned official Home Assistant hassfest image. No application logic, account
configuration, release version or published integration changes are included.

The original Sunday00UTC cadence must be enabled only after a complete initial
pass. GitHub remains the identical public recovery/manual-download consumer,
with Actions disabled. Neither a CI pass nor a recovery push installs an
integration or establishes a published release.

HACS remains intentionally absent because the repository contains two
integrations. The existing manual installation instructions are preserved.
Never read real authentication files or invoke live account/reset/model/device
operations as tests; all current tests use synthetic local data.
