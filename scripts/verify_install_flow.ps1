$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install build
python -m build --sdist --wheel

python -m venv .venv_pkgtest
.\.venv_pkgtest\Scripts\python.exe -m pip install dist\*.whl
.\.venv_pkgtest\Scripts\api2.exe --help

Write-Host "Package build and install verification completed."
