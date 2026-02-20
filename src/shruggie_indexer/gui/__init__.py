"""GUI application for shruggie-indexer.

The GUI requires the ``customtkinter`` package which is available via the
``gui`` install extra::

    pip install shruggie-indexer[gui]

The ``main()`` function is guarded by an ``ImportError`` check so that CLI-only
installations do not crash on import.
"""

__all__ = ["main"]


def main() -> None:
    """Launch the Shruggie Indexer GUI.

    Delegates to :func:`shruggie_indexer.gui.app.main`.  If ``customtkinter``
    is not installed, prints a user-friendly message and exits with code 1.
    """
    try:
        from shruggie_indexer.gui.app import main as _app_main
    except ImportError:
        import sys

        print(
            "Error: The GUI requires 'customtkinter'.\n"
            "Install it with:  pip install shruggie-indexer[gui]",
            file=sys.stderr,
        )
        sys.exit(1)
    _app_main()
