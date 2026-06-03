#!/usr/bin/env python3
import sqlite3
import time


DB_PATH = "/home/docker/new-api/data/one-api.db"
INTERVAL_SECONDS = 5


def sync_once():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("pragma busy_timeout=10000")
        conn.execute(
            """
            update tokens
               set [group] = (select users.[group] from users where users.id = tokens.user_id)
             where exists (
                   select 1
                     from users
                    where users.id = tokens.user_id
                      and coalesce(users.[group], '') <> coalesce(tokens.[group], '')
             )
            """
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    while True:
        try:
            sync_once()
        except Exception:
            pass
        time.sleep(INTERVAL_SECONDS)
