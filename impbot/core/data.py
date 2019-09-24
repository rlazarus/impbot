import logging
import sqlite3
import sys
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)
_db: Optional[str] = None


def startup(db: str) -> None:
    global _db
    assert _db is None, "data.startup() already called"
    _db = db

    conn = sqlite3.connect(db, uri=True)
    with conn:
        conn.execute("PRAGMA FOREIGN_KEYS = on")
        if not _table_exists(conn, "keys"):
            if _table_exists(conn, "impbot"):
                logger.critical(f"{db} is in the old incompatible format!")
                sys.exit(1)
            if ":memory:" not in _db and "mode=memory" not in _db:
                logger.warning("Database doesn't exist -- creating a new one. "
                               "Welcome! :)")

            conn.executescript("""
                CREATE TABLE keys (key_id    INTEGER PRIMARY KEY,
                                   namespace TEXT,
                                   key       TEXT);
                CREATE UNIQUE INDEX idx_keys_nk ON keys (namespace, key);

                CREATE TABLE key_values (key_id INT
                                                REFERENCES keys (key_id)
                                                ON DELETE CASCADE,
                                         value  TEXT);
                CREATE UNIQUE INDEX idx_kv_keyid ON key_values (key_id);
            """)
    conn.close()


def _table_exists(conn, table) -> bool:
    c = conn.execute("SELECT name FROM sqlite_master "
                     "WHERE type='table' AND name=?", (table,))
    return bool(c.fetchone())


def shutdown() -> None:
    global _db
    _db = None


class Namespace(object):
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            assert _db, "data.startup() not called"
            self._conn = sqlite3.connect(_db, uri=True)
            self._conn.execute("PRAGMA FOREIGN_KEYS = on")
        return self._conn

    def get(self, key: str) -> str:
        c = self.conn.execute("SELECT value FROM keys INNER JOIN key_values "
                              "ON keys.rowid = key_values.key_id "
                              "WHERE namespace=? AND key=?",
                              (self.namespace, key))
        row = c.fetchone()
        if row:
            return row[0]
        raise KeyError

    def set(self, key: str, value: str) -> None:
        with self.conn:
            c = self.conn.execute(
                "SELECT key_id FROM keys WHERE namespace=? AND key=?",
                (self.namespace, key))
            row = c.fetchone()
            if row:
                key_id = row[0]
            else:
                c = self.conn.execute(
                    "INSERT INTO keys (namespace, key) VALUES(?, ?)",
                    (self.namespace, key))
                key_id = c.lastrowid
            self.conn.execute("REPLACE INTO key_values VALUES (?,?)",
                              (key_id, value))

    def unset(self, key: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM keys WHERE namespace=? AND key=?",
                              (self.namespace, key))

    def exists(self, key: str) -> bool:
        c = self.conn.execute("SELECT * FROM keys WHERE namespace=? AND key=?",
                              (self.namespace, key))
        return c.fetchone() is not None

    def clear_all(self, key_pattern: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM keys "
                              "WHERE namespace=? AND key LIKE ?",
                              (self.namespace, key_pattern,))

    # TODO: This isn't the right interface -- it was added in a hurry to support
    #  a stream in progress.
    def list(self, key_endswith: str) -> List[Tuple[str, str]]:
        c = self.conn.execute(
            "SELECT key, value FROM "
            "keys INNER JOIN key_values ON keys.rowid = key_values.key_id "
            "WHERE namespace=?",
            (self.namespace,))
        rows = c.fetchall()
        return [(row[0], row[1]) for row in rows
                if row[0].endswith(key_endswith)]
