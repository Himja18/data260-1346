"""Create a login user.
Usage: python create_user.py --name "Dispatcher 1346" --email dispatcher1346@transit.test --password 'TransitLine22!'
"""
import argparse

from database import db_session_basede26
from models import User
from security import hash_password


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    args = p.parse_args()

    db = db_session_basede26()
    try:
        email = args.email.lower()
        if db.query(User).filter(User.email == email).first():
            print(f"User {email} already exists")
            return
        user = User(name=args.name, email=email, password_hash=hash_password(args.password))
        db.add(user)
        db.commit()
        print(f"Created user id={user.id} email={email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
