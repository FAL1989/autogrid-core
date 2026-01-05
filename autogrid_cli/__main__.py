"""CLI entrypoint for python -m autogrid_cli."""

from autogrid_cli.app import app


def main() -> None:
    """Run the AutoGrid CLI."""
    app()


if __name__ == "__main__":
    main()
