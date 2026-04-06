"""CLI utility for ad-hoc task submission to the Foundry API."""

import argparse


def main() -> None:
    """Parse args and submit a task."""
    parser = argparse.ArgumentParser(description="Submit a task to Unicorn Foundry")
    parser.add_argument("--task-type", required=True, help="Task type to execute")
    parser.add_argument("--repo", required=True, help="Target repository")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--prompt", required=True, help="Task prompt")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Foundry API URL")
    _args = parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
