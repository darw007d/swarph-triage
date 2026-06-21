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

    import json

    from swarph_triage import open as open_triage

    q = open_triage(args.db_url)

    # Verbs that map to a state transition / reopen.
    _TRANSITION_VERBS = {
        "approve": "approved",
        "wontfix": "wontfix",
        "escalate": "needs_review",
    }

    if args.cmd == "list":
        rows = q.list(status=args.status)
        if not rows:
            print("(queue empty)")
        for r in rows:
            print(f"{r['id']:>5}  {r['priority_score']:>7.2f}  "
                  f"{r['status']:<12}  {r['severity']:<8}  {r['fingerprint']}")
        return 0

    if args.cmd == "stats":
        print(json.dumps(q.stats(), indent=2, default=str))
        return 0

    if args.cmd == "show":
        row = q.show(args.id)
        if not row:
            print(f"ERROR: no fingerprint id={args.id}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2, default=str))
        return 0

    if args.cmd in _TRANSITION_VERBS:
        ok = q.transition(
            args.id,
            to_status=_TRANSITION_VERBS[args.cmd],
            actor="cli",
            note=args.note,
        )
        if not ok:
            print(f"ERROR: {args.cmd} on id={args.id} rejected "
                  f"(invalid transition or missing row)", file=sys.stderr)
            return 1
        print(f"{args.cmd}: id={args.id} -> {_TRANSITION_VERBS[args.cmd]}")
        return 0

    if args.cmd == "reopen":
        ok = q.reopen(args.id, actor="cli", note=args.note)
        if not ok:
            print(f"ERROR: reopen on id={args.id} rejected "
                  f"(not terminal or missing row)", file=sys.stderr)
            return 1
        print(f"reopen: id={args.id} -> new")
        return 0

    if args.cmd == "history":
        hist = q.history(args.id)
        if not hist:
            print("(no history)")
        for h in hist:
            print(f"{h['transitioned_at']}  {h['from_status']} -> "
                  f"{h['to_status']}  [{h['actor']}]  {h['note'] or ''}")
        return 0

    if args.cmd == "backlog":
        print(q.backlog_md())
        return 0

    print(f"ERROR: unknown command {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
