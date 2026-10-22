"""Create (or update) a login user for the HW7 JWT API.

    python create_user.py --username writer1346 --role writer      # prompts for the password
    HW7_USER_PASSWORD=... python create_user.py --username reader1346 --role reader

The password is read from HW7_USER_PASSWORD or typed at a prompt (never a command-line
argument, never stored in the repo) and saved only as a PBKDF2-SHA256 hash.
"""
import argparse
import getpass
import os

from database import db_session_basede26
from models import ROLES, User
from security import hash_password


def main() -> None:
    """Insert the user, or update password/role if the username exists."""
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--role", choices=ROLES, required=True)
    p.add_argument("--name", default=None)
    args = p.parse_args()
    password = os.getenv("HW7_USER_PASSWORD") or getpass.getpass(f"Password for {args.username}: ")
    if len(password) < 8:
        raise SystemExit("password must be at least 8 characters")

    username = args.username.strip().lower()
    db = db_session_basede26()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(username=username, role=args.role, name=args.name,
                        password_hash=hash_password(password))
            db.add(user)
            action = "Created"
        else:
            user.role, user.password_hash = args.role, hash_password(password)
            action = "Updated"
        db.commit()
        print(f"{action} user id={user.id} username={username} role={user.role}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
