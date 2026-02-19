"""Enable ``python -m shruggie_indexer`` invocation."""

import sys


def main() -> None:
    """Import and run the CLI entry point."""
    try:
        from shruggie_indexer.cli.main import main as cli_main
    except ImportError:
        print(
            "The CLI requires the 'click' package.\n"
            "Install it with: pip install shruggie-indexer",
            file=sys.stderr,
        )
        sys.exit(1)
    cli_main()


if __name__ == "__main__":
    main()
