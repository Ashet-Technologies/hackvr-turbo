"""Manual script to validate network connections."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import time

from hackvr import net


def run_server(host: str, port: int) -> None:
    server = net.RawServer(host, port)
    print(f"Listening on {host}:{port} ...")
    result = server.accept()
    assert result is not None
    peer, token = result
    print("Accepted connection:", token)
    peer.send(b"ping\r\n")
    for _ in range(20):
        data = peer.receive()
        if data:
            print("Received:", data)
            break
        time.sleep(0.1)
    peer.close()
    server.close()


def run_client(url: str) -> None:
    client = net.Client()
    token = client.connect(url)
    print("Connected:", token)
    client.send(b"pong\r\n")
    for _ in range(20):
        data = client.receive()
        if data:
            print("Received:", data)
            break
        time.sleep(0.1)
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual HackVR net test script.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    server_parser = subparsers.add_parser("server", help="Run a test server.")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=net.HACKVR_PORT)

    client_parser = subparsers.add_parser("client", help="Run a test client.")
    client_parser.add_argument("url", help="HackVR URL (e.g. hackvr://127.0.0.1:1913)")

    args = parser.parse_args()
    if args.mode == "server":
        run_server(args.host, args.port)
    else:
        run_client(args.url)


if __name__ == "__main__":
    main()
