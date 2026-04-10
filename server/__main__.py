"""CLI entry point for server management commands.

Usage:
    python -m server ingest
    python -m server mint-token --email you@gmail.com [--expiry-days 365]
"""

import argparse
import sys


def cmd_ingest(args):
    from server.ingest import run_ingestion
    run_ingestion()


def cmd_mint_token(args):
    from server.config import JWT_SECRET
    from server.auth import create_api_token
    from server.database import get_db

    if not JWT_SECRET:
        print("Error: JWT_SECRET not set.", file=sys.stderr)
        sys.exit(1)

    with get_db() as conn:
        row = conn.execute(
            "SELECT email, display_name, role FROM users WHERE email = %s",
            (args.email,),
        ).fetchone()

    if not row:
        print(f"Error: No user '{args.email}'. Must log in via web UI first.", file=sys.stderr)
        sys.exit(1)

    if row["role"] not in ("readwrite", "admin"):
        print(f"Error: User role '{row['role']}' insufficient. Need readwrite or admin.", file=sys.stderr)
        sys.exit(1)

    token = create_api_token(
        email=row["email"],
        name=row["display_name"] or "",
        expiry_days=args.expiry_days,
    )
    print(f"Token minted for {row['email']} (role: {row['role']}), expires in {args.expiry_days} days.", file=sys.stderr)
    print(token)  # bare token to stdout for capture


def main():
    parser = argparse.ArgumentParser(prog="python -m server")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Ingest ride data from JSON files")

    mint = sub.add_parser("mint-token", help="Mint a long-lived API token for cron use")
    mint.add_argument("--email", required=True, help="Email of an existing user")
    mint.add_argument("--expiry-days", type=int, default=365, help="Token lifetime in days (default: 365)")

    args = parser.parse_args()
    {"ingest": cmd_ingest, "mint-token": cmd_mint_token}[args.command](args)


if __name__ == "__main__":
    main()
