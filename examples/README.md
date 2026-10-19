# Example Library

This directory is the **example library** used by the README demo and the evaluation fixture. It is not auto-loaded.

- `entries/` contains 12 Markdown experience entries.
- To use it as a local library, point `CAIRN_HOME` at this directory.
- Runtime data is written to `cache/` and `log/`, both gitignored.
- For real use, keep your own library under `~/.cairn` (or another `CAIRN_HOME`).

```bash
CAIRN_HOME=./examples python3 cairn.py recall "docker compose config 密钥"
```

These entries are demonstrations, not verified production knowledge.
