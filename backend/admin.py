"""Initialize the first administrator; password is read interactively, never committed."""

import argparse, getpass, json
from werkzeug.security import generate_password_hash
from .app import create_app
from .domain import uid

p = argparse.ArgumentParser()
p.add_argument("command", choices=["init-admin"])
p.add_argument("--username", default="admin")
args = p.parse_args()
app = create_app()
with app.connect() as c:
    if c.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone():
        raise SystemExit(
            "Administrator already exists; use the account management page."
        )
    password = getpass.getpass("New administrator password (minimum 12 characters): ")
    if len(password) < 12 or password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords must match and contain at least 12 characters.")
    c.execute(
        "INSERT INTO users VALUES(?,?,?,?,?,?,?,?)",
        (
            uid("USR"),
            args.username.lower(),
            "Administrator",
            generate_password_hash(password),
            "admin",
            "[]",
            None,
            1,
        ),
    )
print("Administrator created.")
