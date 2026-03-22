"""
AWS Resource Lifecycle Tracker — Management CLI
Run on EC2 over SSH for management operations that require DB write access.

Usage:
    python manage.py poller run-now
    python manage.py alerts list
    python manage.py alerts acknowledge <id>
    python manage.py alerts resolve <id>
    python manage.py resources list
    python manage.py snapshot generate
    python manage.py db cleanup

Phase 0: Commands are defined but print "not implemented yet".
Full implementation added per phase.
"""

import sys


def usage():
    print("""
AWS Resource Lifecycle Tracker — manage.py

Usage:
    python manage.py <command> [args]

Commands:
    poller run-now               Trigger an immediate poll cycle
    alerts list                  List all active alerts
    alerts acknowledge <id>      Acknowledge an alert by ID
    alerts resolve <id>          Manually resolve an alert by ID
    resources list               List all active resources
    snapshot generate            Generate and upload static snapshot now
    db cleanup                   Run database cleanup jobs manually

Phase 0: Commands are registered but not yet implemented.
""")


def cmd_poller(args):
    if not args or args[0] != "run-now":
        print("Usage: python manage.py poller run-now")
        sys.exit(1)
    print("[Phase 3] poller run-now — not implemented yet")


def cmd_alerts(args):
    if not args:
        print("Usage: python manage.py alerts <list|acknowledge|resolve> [id]")
        sys.exit(1)

    sub = args[0]
    if sub == "list":
        print("[Phase 5] alerts list — not implemented yet")
    elif sub == "acknowledge":
        if len(args) < 2:
            print("Usage: python manage.py alerts acknowledge <id>")
            sys.exit(1)
        print(f"[Phase 5] alerts acknowledge {args[1]} — not implemented yet")
    elif sub == "resolve":
        if len(args) < 2:
            print("Usage: python manage.py alerts resolve <id>")
            sys.exit(1)
        print(f"[Phase 5] alerts resolve {args[1]} — not implemented yet")
    else:
        print(f"Unknown alerts subcommand: {sub}")
        sys.exit(1)


def cmd_resources(args):
    if not args or args[0] != "list":
        print("Usage: python manage.py resources list")
        sys.exit(1)
    print("[Phase 4] resources list — not implemented yet")


def cmd_snapshot(args):
    if not args or args[0] != "generate":
        print("Usage: python manage.py snapshot generate")
        sys.exit(1)
    print("[Phase 8] snapshot generate — not implemented yet")


def cmd_db(args):
    if not args or args[0] != "cleanup":
        print("Usage: python manage.py db cleanup")
        sys.exit(1)
    print("[Phase 4] db cleanup — not implemented yet")


COMMANDS = {
    "poller":    cmd_poller,
    "alerts":    cmd_alerts,
    "resources": cmd_resources,
    "snapshot":  cmd_snapshot,
    "db":        cmd_db,
}


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        usage()
        sys.exit(0)

    command = args[0]
    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        usage()
        sys.exit(1)

    COMMANDS[command](args[1:])


if __name__ == "__main__":
    main()