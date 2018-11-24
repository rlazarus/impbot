import logging
import sqlite3

import bot

_conn: sqlite3.Connection = None


def startup(db: str) -> None:
    global _conn
    assert _conn is None, "data.init() already called"
    _conn = sqlite3.connect(db)
    c = _conn.execute("SELECT name FROM sqlite_master "
                      "WHERE type='table' AND name='impbot'")
    if not c.fetchone():
        if db != ":memory:":
            logging.warning("Database doesn't exist -- creating a new one. "
                            "Welcome! :)")
        c.execute("CREATE TABLE impbot "
                  "(handler_class TEXT, key TEXT, value TEXT, "
                  "PRIMARY KEY(handler_class, key))")
    _conn.commit()


def shutdown() -> None:
    global _conn
    assert _conn, "data.init() not called"
    _conn.close()
    _conn = None


def get(handler: bot.Handler, key: str, default: str = None) -> str:
    assert _conn, "data.init() not called"
    c = _conn.execute("SELECT value FROM impbot "
                      "WHERE handler_class=? AND key=?",
                      (handler.__class__.__name__, key))
    row = c.fetchone()
    if row:
        return row[0]
    return default


def set(handler: bot.Handler, key: str, value: str) -> None:
    assert _conn, "data.init() not called"
    _conn.execute("REPLACE INTO impbot VALUES(?,?,?)",
                  (handler.__class__.__name__, key, value))
    _conn.commit()


def unset(handler: bot.Handler, key: str) -> None:
    assert _conn, "data.init() not called"
    _conn.execute("DELETE FROM impbot WHERE handler_class=? AND key=?",
                  (handler.__class__.__name__, key))
    _conn.commit()


def exists(handler: bot.Handler, key: str) -> bool:
    assert _conn, "data.init() not called"
    c = _conn.execute("SELECT value FROM impbot "
                      "WHERE handler_class=? AND key=?",
                      (handler.__class__.__name__, key))
    return c.fetchone() is not None
