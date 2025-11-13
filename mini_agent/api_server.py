"""
Mini Agent API Server - Command-line entry point

This script starts the HTTP API server for Mini Agent.
"""

import argparse
import sys

import uvicorn


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Mini Agent API Server - HTTP API with OpenAPI documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mini-agent-api                           # Start server on default port 8000
  mini-agent-api --port 8080              # Start on custom port
  mini-agent-api --host 0.0.0.0           # Listen on all interfaces
  mini-agent-api --reload                 # Enable auto-reload for development
        """,
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development (watches for code changes)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Logging level (default: info)",
    )

    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="mini-agent-api 0.1.0",
    )

    return parser.parse_args()


def main():
    """Main entry point for API server"""
    args = parse_args()

    print("=" * 60)
    print("🚀 Mini Agent API Server")
    print("=" * 60)
    print(f"📍 Server URL: http://{args.host}:{args.port}")
    print(f"📖 API Docs:   http://{args.host}:{args.port}/docs")
    print(f"📄 OpenAPI:    http://{args.host}:{args.port}/openapi.json")
    print(f"📚 ReDoc:      http://{args.host}:{args.port}/redoc")
    print("=" * 60)
    print()

    try:
        uvicorn.run(
            "mini_agent.api:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,  # reload only works with 1 worker
            log_level=args.log_level,
        )
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
