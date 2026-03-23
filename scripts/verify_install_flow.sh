#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install build
python -m build --sdist --wheel

python -m venv .venv_pkgtest
source .venv_pkgtest/bin/activate
pip install dist/*.whl
api2 --help

echo "Package build and install verification completed."
