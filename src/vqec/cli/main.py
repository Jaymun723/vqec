import argparse
import sys
import os

import vqec

def handle_server(args):
    """Starts the FastAPI REST server."""
    import uvicorn

    print(f"Starting VQEC Server on http://{args.host}:{args.port}...")
    uvicorn.run("vqec.server.main:app", host=args.host, port=args.port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(
        prog="vqec",
        description="VQEC (Visualise QEC): A library for simulating and analyzing QEC codes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {vqec.__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Server Command
    server_parser = subparsers.add_parser("server", help="Start the FastAPI REST server")
    server_parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the server to")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    server_parser.add_argument("--reload", action="store_true", help="Enable automatic hot-reloading")
    server_parser.set_defaults(func=handle_server)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
