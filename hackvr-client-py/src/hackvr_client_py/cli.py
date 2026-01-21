"""Command-line entrypoint for the HackVR client."""

from __future__ import annotations

import argparse

from hackvr_client_py.client import run_client


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(prog="hackvr-client-py", description="HackVR raylib client")
    parser.add_argument("address", help="Server address to connect to")
    return parser.parse_args()


def main() -> None:
    """Run the client."""
    args = parse_args()
    run_client(args.address)


if __name__ == "__main__":
    main()
