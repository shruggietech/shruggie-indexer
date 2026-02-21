# Testing & Lint Troubleshooting

This page documents practical recovery steps for contributor environments where testing appears to hang or where the editor becomes unresponsive during linting.

## Symptom: VS Code freezes during `ruff`

If your session freezes specifically when linting starts, the most common trigger in this project is running Ruff against the full repository (`ruff check .`) from an IDE-integrated terminal with heavy output rendering.

In this repository, Ruff is configured with `src = ["src"]` in `pyproject.toml`, and the delivery plan calls out `ruff check src/` as the expected lint command.

### Why this matters

`ruff check .` includes test and docs trees, which can produce a large number of findings in one run. That is unnecessary for release readiness, because release automation currently runs pytest and build steps (not Ruff) on tag push.

## Recommended command sequence (safe baseline)

Run these from a standalone terminal (PowerShell, CMD, or external bash), not from a busy VS Code integrated terminal:

```bash
python -m pytest tests/ -m "not requires_exiftool"
ruff check src/
```

Optional: if you need test linting too, run it separately:

```bash
ruff check tests/
```

Splitting lint scope makes failures easier to read and avoids terminal flood in a single command.

## If VS Code still freezes

1. Disable Ruff's editor integration temporarily and run Ruff only from the terminal.
2. Run lint with narrower scope (`ruff check src/` first).
3. Redirect lint output to a file for inspection:

   ```bash
   ruff check src/ > ruff.log
   ```

4. Re-open VS Code with all extensions disabled once (`code --disable-extensions`) to isolate extension conflicts.
5. Re-enable extensions one by one, starting with Python and Ruff.

## Release-blocking triage checklist

Use this order before cutting the first release tag:

1. `pytest tests/ -m "not requires_exiftool"`
2. `ruff check src/`
3. Optional: `ruff check tests/`
4. Build script (`scripts/build.sh` or `scripts/build.ps1`)

If step 1 and step 4 pass, you can still validate release packaging behavior even if test linting cleanup is deferred.
