"""Online SQLite backup includes records, users, sessions, audit, and private evidence."""

import argparse, os, sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("output")
a = p.parse_args()
target = Path(a.output)
if target.exists():
    raise SystemExit("Refusing to overwrite an existing backup.")
source = os.environ.get("DATABASE_PATH", "data/manifest.sqlite3")
if not Path(source).exists():
    raise SystemExit("Source database does not exist.")
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    result = dst.execute("PRAGMA integrity_check").fetchone()[0]
os.chmod(target, 0o600)
if result != "ok":
    raise SystemExit("Integrity check failed: " + result)
print("Backup completed and integrity checked.")
