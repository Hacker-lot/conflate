# Changelog

## 0.4.0

Conflate now has explicit block interfaces alongside its original implicit
sharing syntax. A marker such as `@cpp(in: seed: int; out: answer: int)` declares
the values a block consumes and publishes. Runtime checks catch missing values
and incompatible boundary types.

- Added a language specification and a typed Python/C++ pipeline example.
- Added `--run-source`, `--build`, `--run-build`, and `--doctor`.
- Local builds preserve a source snapshot, manifest, and prepared native cache
  without executing program statements during the build.
- Retained bare language markers, registered backends, and persistent
  cross-language function workers.
- CI runs the test suite on Python 3.11 and 3.13 with native toolchains.

This remains an experimental process-based language runtime. Local builds are
not standalone binaries. Native declaration discovery and function signatures
still have the restrictions documented in `DOCUMENTATION.md`.
