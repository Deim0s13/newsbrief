from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """
    Dispatches to the right maintenance-CLI module by subcommand name.

    Each module (``embed_backfill``, ``entity_backfill``, ...) owns its own
    argparse subparser and stays fully self-contained; this just routes the
    first argv token to the module that defines it, so ``python -m app.cli``
    can grow new subcommands without turning into one big shared parser.
    """
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else None

    if command == "entity-backfill":
        from app.entity_backfill import main_cli as entity_main_cli

        return entity_main_cli(args)

    from app.embed_backfill import main_cli as embed_main_cli

    return embed_main_cli(args)


if __name__ == "__main__":
    sys.exit(main())
