from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def _cmd_not_implemented(_args: argparse.Namespace) -> int:
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apifoxcli")
    sub = parser.add_subparsers(dest="resource", required=True)

    project_parser = sub.add_parser("project")
    project_sub = project_parser.add_subparsers(dest="action", required=True)
    project_init = project_sub.add_parser("init")
    project_init.add_argument("--project-root", default=".")
    project_init.set_defaults(handler=_cmd_not_implemented)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--project-root", default=".")
    validate_parser.set_defaults(resource="validate", action="run", handler=_cmd_not_implemented)

    api_parser = sub.add_parser("api")
    api_sub = api_parser.add_subparsers(dest="action", required=True)
    api_send = api_sub.add_parser("send")
    api_send.add_argument("resource_id")
    api_send.add_argument("--project-root", default=".")
    api_send.add_argument("--env", default=None)
    api_send.add_argument("--json", action="store_true")
    api_send.set_defaults(handler=_cmd_not_implemented)

    suite_parser = sub.add_parser("suite")
    suite_sub = suite_parser.add_subparsers(dest="action", required=True)
    suite_run = suite_sub.add_parser("run")
    suite_run.add_argument("resource_id")
    suite_run.add_argument("--project-root", default=".")
    suite_run.add_argument("--env", default=None)
    suite_run.add_argument("--json", action="store_true")
    suite_run.set_defaults(handler=_cmd_not_implemented)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
