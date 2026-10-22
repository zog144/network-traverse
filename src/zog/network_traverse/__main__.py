"""network-traverse local CLI; all mapping mutation remains opt-in."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .agent import Agent
from .server import InspectServer
from .storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(prog="network-traverse")
    parser.add_argument("--state-dir", default="/state/network-traverse")
    parser.add_argument("--socket", default="/run/network-traverse/inspect.sock")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("initialize-only")
    sub.add_parser("inspect")
    sub.add_parser("reconcile-once")
    server = sub.add_parser("serve")
    server.add_argument("--interval", type=float, default=30)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        store = Storage(args.state_dir)
        store.initialize()
        if args.command == "initialize-only":
            return 0
        agent = Agent(store)
        if args.command == "inspect":
            print(json.dumps(agent.inspect(), indent=2, sort_keys=True))
            return 0
        with store.daemon_lock():
            if args.command == "reconcile-once":
                print(json.dumps(agent.reconcile(), indent=2, sort_keys=True))
                return 0
            InspectServer(agent, args.socket).serve_forever(interval_seconds=args.interval)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
