#!/usr/bin/env python3
import sqlite3
import time


DB_PATH = "/home/docker/new-api/data/one-api.db"
INTERVAL_SECONDS = 5


def sync_once():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("pragma busy_timeout=10000")
        groups = [
            row[0]
            for row in conn.execute(
                "select distinct [group] from users where coalesce([group], '') <> ''"
            )
        ]

        # Existing API keys should always use the group currently selected by admin.
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

        # Channels may be assigned to default-like visible groups only. Ensure every
        # real user group can route through the same enabled channel abilities.
        for group in groups:
            conn.execute(
                """
                update channels
                   set [group] = [group] || ',' || ?
                 where coalesce([group], '') <> ''
                   and (',' || [group] || ',') not like '%,' || ? || ',%'
                   and status = 1
                """,
                (group, group),
            )
            conn.execute(
                """
                insert or ignore into abilities([group], model, channel_id, enabled, priority, weight, tag)
                select ?, model, channel_id, enabled, priority, weight, tag
                  from abilities
                 where [group] in ('default', 'default1')
                """,
                (group,),
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
