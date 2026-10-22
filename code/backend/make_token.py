"""Mint a JWT for testing (HW7 Part 1 - the expired-token screenshot).

    JWT_SECRET=... python make_token.py --username reader1346 --minutes -5   # already expired

Uses the same JWT_SECRET and signing code as the running server, so the only
thing wrong with a negative-lifetime token is its expiry.
"""
import argparse
from datetime import timedelta

from auth import create_access_token
from database import db_session_basede26
from models import User


def main() -> None:
    """Print a token for an existing user with the requested lifetime."""
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--minutes", type=float, default=-5, help="lifetime; negative = expired")
    args = p.parse_args()
    db = db_session_basede26()
    try:
        user = db.query(User).filter(User.username == args.username.lower()).first()
        if user is None:
            raise SystemExit(f"no user {args.username}")
        print(create_access_token(user, timedelta(minutes=args.minutes)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
