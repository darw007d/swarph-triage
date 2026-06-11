"""CLI — pure SQL, no LLM, instant.

Reads ``SWARPH_TRIAGE_DB_URL`` from env. Implementation lands with queue port.
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swarph-triage")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("SWARPH_TRIAGE_DB_URL"),
        help="Database URL (defaults to $SWARPH_TRIAGE_DB_URL).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show top of queue").add_argument(
        "--status", help="Filter by status", default=None,
    )
    sub.add_parser("stats", help="Status + category breakdown")
    p_show = sub.add_parser("show", help="Show one row + history")
    p_show.add_argument("id", type=int)
    for verb in ("approve", "wontfix", "escalate", "reopen"):
        p = sub.add_parser(verb, help=f"{verb} a fingerprint")
        p.add_argument("id", type=int)
        p.add_argument("note", nargs="?", default="")
    p_hist = sub.add_parser("history", help="Show state_log for one row")
    p_hist.add_argument("id", type=int)
    sub.add_parser("backlog", help="Print queue as markdown")

    args = parser.parse_args(argv)
    if not args.db_url:
        print("ERROR: --db-url or $SWARPH_TRIAGE_DB_URL required", file=sys.stderr)
        return 2

    # Implementation pending — wires args → TriageQueue method calls.
    print(f"swarph-triage {args.cmd}: implementation in flight (db={args.db_url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
