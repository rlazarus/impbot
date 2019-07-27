import logging
import sqlite3
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)
_db: Optional[str] = None


def startup(db: str) -> None:
    global _db
    assert _db is None, "data.startup() already called"
    _db = db

    conn = sqlite3.connect(db, uri=True)
    c = conn.execute("SELECT name FROM sqlite_master "
                     "WHERE type='table' AND name='impbot'")
    if not c.fetchone():
        if ":memory:" not in _db and "mode=memory" not in _db:
            logger.warning("Database doesn't exist -- creating a new one. "
                           "Welcome! :)")
        conn.execute("CREATE TABLE impbot "
                     "(handler_class TEXT, key TEXT, value TEXT, "
                     "PRIMARY KEY(handler_class, key))")
    conn.commit()
    conn.close()


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
        return self._conn

    def get(self, key: str, default: Optional[str] = None) -> str:
        c = self.conn.execute("SELECT value FROM impbot "
                              "WHERE handler_class=? AND key=?",
                              (self.namespace, key))
        row = c.fetchone()
        if row:
            return row[0]
        if default is None:
            raise KeyError
        return default

    def set(self, key: str, value: str) -> None:
        self.conn.execute("REPLACE INTO impbot VALUES(?,?,?)",
                          (self.namespace, key, value))
        self.conn.commit()

    def unset(self, key: str) -> None:
        self.conn.execute("DELETE FROM impbot "
                          "WHERE handler_class=? AND key=?",
                          (self.namespace, key))
        self.conn.commit()

    def exists(self, key: str) -> bool:
        c = self.conn.execute("SELECT value FROM impbot "
                              "WHERE handler_class=? AND key=?",
                              (self.namespace, key))
        return c.fetchone() is not None

    def clear_all(self, key_pattern: str) -> None:
        self.conn.execute("DELETE FROM impbot "
                          "WHERE HANDLER_class=? AND key LIKE ?",
                          (self.namespace, key_pattern,))
        self.conn.commit()

    # TODO: This isn't the right interface -- it was added in a hurry to support
    #  a stream in progress.
    def list(self, key_endswith: str) -> List[Tuple[str, str]]:
        c = self.conn.execute("SELECT key, value FROM impbot "
                              "WHERE handler_class=?",
                              (self.namespace,))
        rows = c.fetchall()
        return [(row[0], row[1]) for row in rows
                if row[0].endswith(key_endswith)]
