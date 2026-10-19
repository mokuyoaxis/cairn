# Example Library

This directory is the **example library** used by the README demo and the evaluation fixture. It is not auto-loaded.

- `entries/` contains 12 Markdown experience entries.
- The entries carry demo contract metadata (`status: active`, `trust: verified`,
  `verified_at: 2026-10-19`) so the fixture can exercise automatic injection.
  This is fixture metadata, not production verification.
- To use it as a local library, point `CAIRN_HOME` at this directory.
- Runtime data is written to `cache/` and `log/`, both gitignored.
- For real use, keep your own library under `~/.cairn` (or another `CAIRN_HOME`).

```bash
CAIRN_HOME=./examples python3 cairn.py recall "docker compose config 密钥"
```

These entries are demonstrations, not verified production knowledge. Treat the
`trust: verified` marker as fixture setup, not as evidence that the advice is
correct in your environment.
