import inspect
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


def _handler_classname() -> str:
    """The name of the Handler subclass that called us."""
    stack = inspect.stack()
    for frame in stack:
        self = frame[0].f_locals.get("self", None)
        if isinstance(self, bot.Handler):
            return self.__class__.__name__
    raise ValueError("Not called by a Handler subclass.")


def get(key: str, default: str = None) -> str:
    assert _conn, "data.init() not called"
    c = _conn.execute("SELECT value FROM impbot "
                      "WHERE handler_class=? AND key=?",
                      (_handler_classname(), key))
    row = c.fetchone()
    if row:
        return row[0]
    return default


def set(key: str, value: str) -> None:
    assert _conn, "data.init() not called"
    _conn.execute("REPLACE INTO impbot VALUES(?,?,?)",
                  (_handler_classname(), key, value))
    _conn.commit()


def unset(key: str) -> None:
    assert _conn, "data.init() not called"
    _conn.execute("DELETE FROM impbot WHERE handler_class=? AND key=?",
                  (_handler_classname(), key))
    _conn.commit()


def exists(key: str) -> bool:
    assert _conn, "data.init() not called"
    c = _conn.execute("SELECT value FROM impbot "
                      "WHERE handler_class=? AND key=?",
                      (_handler_classname(), key))
    return c.fetchone() is not None
