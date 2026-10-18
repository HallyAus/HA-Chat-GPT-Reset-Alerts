# Existing metadata witness correction

The first private run478 passed22unit tests and failed the remaining metadata
test because it still expected Claude Usage0.1.0. The existing source manifest
already declares0.1.1; this migration did not change it. The test now asserts
that existing exact source version, retaining all domain, translation and
packaging assertions. Runtime, provider/authentication/reset/polling behavior,
versions and publication state are unchanged. Full Linux validation and
official hassfest remain required before identical recovery or scheduling.
