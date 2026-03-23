# Release Process and Versioning Strategy

This document defines how to version, verify, and publish `pytest-auto-api2-cli`.

> Canonical release documentation location: [`docs/release-package-guide.md`](docs/release-package-guide.md).  
> This file is kept as a quick summary/entry.

## Versioning Strategy

We use Semantic Versioning (`MAJOR.MINOR.PATCH`):

- MAJOR: incompatible CLI/runtime or package layout changes.
- MINOR: backward-compatible features (new CLI options, new workflows).
- PATCH: backward-compatible fixes and test-only changes.

Version sources that must stay aligned:

- `pyproject.toml` -> `[project].version`
- `pytest_auto_api2/__init__.py` -> `__version__`

## Release Checklist

1. Update version in both files listed above.
2. Update `TASK_PROGRESS.md` and migration/release notes as needed.
3. Run local verification:

```bash
python -m pytest -q tests_phase3
python -m compileall -q common utils pytest_auto_api2 cli.py run.py tests_phase3
python -m build --sdist --wheel
```

4. Verify wheel installation flow:

```bash
python -m venv .venv_pkgtest
. .venv_pkgtest/bin/activate
pip install dist/*.whl
api2 --help
```

5. Commit and tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Publish via GitHub Actions

Use workflow `.github/workflows/publish.yml` with `workflow_dispatch`:

- target=`testpypi`: publishes to TestPyPI (secret: `TEST_PYPI_API_TOKEN`)
- target=`pypi`: publishes to PyPI (secret: `PYPI_API_TOKEN`)

The workflow always:

1. builds sdist+wheel,
2. verifies fresh wheel installation,
3. publishes only if verification succeeds.

## Rollback Guidance

- Do not overwrite a released version.
- Publish a new PATCH version to fix packaging or runtime issues.
- If a bad release reaches public index, yank it in index UI and release a fixed PATCH.
