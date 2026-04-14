"""Smoke tests.

These are intentionally lightweight so contributors can run `pytest` without
needing AWS credentials or a running database.
"""


def test_manage_cli_parser_builds():
    import manage

    parser = manage.build_parser()
    # argparse keeps subparsers on the internal _subparsers attribute
    subparsers_action = parser._subparsers._group_actions[0]
    choices = set(subparsers_action.choices.keys())

    assert {"poller", "alerts", "resources", "snapshot", "db"}.issubset(choices)
