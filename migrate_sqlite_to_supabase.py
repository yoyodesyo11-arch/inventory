import os
import sqlite3

import requests


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "inventory.db")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL and SUPABASE_KEY are required.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM inventory ORDER BY id")]
    conn.close()

    if not rows:
        print("No rows to migrate.")
        return

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/inventory",
        headers=headers,
        json=rows,
        timeout=30,
    )
    response.raise_for_status()
    print(f"Migrated {len(rows)} rows.")


if __name__ == "__main__":
    main()
