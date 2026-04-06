"""Export run artifacts to local filesystem for inspection."""

import argparse


def main() -> None:
    """Parse args and export artifacts."""
    parser = argparse.ArgumentParser(description="Export artifacts for a Foundry run")
    parser.add_argument("--run-id", required=True, help="Run ID to export")
    parser.add_argument("--output-dir", default="./exported", help="Output directory")
    _args = parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
