#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Backward-compatible CLI shim."""

from pytest_auto_api2.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
