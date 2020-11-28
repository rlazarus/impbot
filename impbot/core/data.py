import itertools
import logging
import sqlite3
import sys
import threading
from typing import List, Optional, Dict, Union, Iterable

logger = logging.getLogger(__name__)
_db: Optional[str] = None
SCHEMA_VERSION = 2


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

            conn.executescript(f"""
                CREATE TABLE keys (key_id    INTEGER PRIMARY KEY,
                                   namespace TEXT,
                                   key       TEXT,
                                   type      TEXT NOT NULL
                                             CHECK (type IN ('KV', 'KKV')));
                CREATE UNIQUE INDEX idx_keys_nk ON keys (namespace, key);

                CREATE TABLE key_values (key_id INT
                                                REFERENCES keys (key_id)
                                                ON DELETE CASCADE,
                                         value  TEXT);
                CREATE UNIQUE INDEX idx_kv_keyid ON key_values (key_id);

                CREATE TABLE key_subkey_values (key_id INT
                                                       REFERENCES keys (key_id)
                                                       ON DELETE CASCADE,
                                                subkey TEXT,
                                                value  TEXT);
                CREATE UNIQUE INDEX idx_kkv_keyid_subkey
                    ON key_subkey_values (key_id, subkey);

                INSERT INTO keys (namespace, key, type)
                    VALUES ('impbot.core.bot.Bot', 'schema_version', 'KV');
                INSERT INTO key_values VALUES (1, '{SCHEMA_VERSION}');
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
        self.thread_local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self.thread_local, "conn"):
            if not _db:
                raise ValueError("data.startup() not called")
            self.thread_local.conn = sqlite3.connect(_db, uri=True)
            self.thread_local.conn.execute("PRAGMA FOREIGN_KEYS = on")
        return self.thread_local.conn

    def get(self, key: str, subkey: Optional[str] = None,
            default: Optional[str] = None) -> str:
        try:
            if subkey is not None:
                key_id = self._find_key(self.conn, key, subkeys=True,
                                        create=False)
                c = self.conn.execute("SELECT value FROM key_subkey_values "
                                      "WHERE key_id=? AND subkey=?",
                                      (key_id, subkey))
            else:
                key_id = self._find_key(self.conn, key, subkeys=False,
                                        create=False)
                c = self.conn.execute("SELECT value FROM key_values "
                                      "WHERE key_id=?", (key_id,))
            row = c.fetchone()
            if row:
                return row[0]
            raise KeyError
        except KeyError:
            # The whole thing is wrapped in a try-except because _find_key() can
            # also raise KeyError, if the key doesn't exist at all.
            if default is not None:
                return default
            raise

    def get_dict(self, key: str) -> Dict[str, str]:
        key_id = self._find_key(self.conn, key, subkeys=True, create=False)
        c = self.conn.execute("SELECT subkey, value FROM key_subkey_values "
                              "WHERE key_id=?", (key_id,))
        return {row[0]: row[1] for row in c}

    def set_subkey(self, key: str, subkey: str, value: str) -> None:
        with self.conn:
            key_id = self._find_key(self.conn, key, subkeys=True, create=True)
            self.conn.execute("REPLACE INTO key_subkey_values VALUES (?,?,?)",
                              (key_id, subkey, value))

    def set(self, key: str, value: Union[str, Dict[str, str]]) -> None:
        if isinstance(value, str):
            with self.conn:
                key_id = self._find_key(self.conn, key, subkeys=False,
                                        create=True)
                self.conn.execute("REPLACE INTO key_values VALUES (?,?)",
                                  (key_id, value))
        else:
            with self.conn:
                key_id = self._find_key(self.conn, key, subkeys=True,
                                        create=True)
                self.conn.execute(
                    "DELETE FROM key_subkey_values WHERE key_id=?", (key_id,))
                for subkey, subvalue in value.items():
                    self.conn.execute(
                        "INSERT INTO key_subkey_values VALUES (?,?,?)",
                        (key_id, subkey, subvalue))

    def increment_subkeys(self, key: str, subkeys: Iterable[str],
                          delta: int = 1) -> None:
        if not subkeys:
            return
        with self.conn:
            key_id = self._find_key(self.conn, key, subkeys=True, create=True)

            # First insert any missing subkeys, starting them at zero...
            qmarks = ",".join("(?, ?, 0)" for _ in subkeys)
            values = tuple(
                itertools.chain.from_iterable((key_id, i) for i in subkeys))
            self.conn.execute(
                f"INSERT OR IGNORE INTO key_subkey_values VALUES {qmarks}",
                values)

            # ... then increment all subkeys, since all are present. (Values are
            # strings, but sqlite lets us add strings like integers, when their
            # values are number-shaped. CAUTION: This overwrites the original
            # value if it wasn't a number.)
            qmarks = ",".join("?" for _ in subkeys)
            self.conn.execute(
                "UPDATE key_subkey_values SET value = value + ? "
                f"WHERE key_id=? AND subkey IN ({qmarks})",
                (delta, key_id) + tuple(subkeys))

    def _find_key(self, conn: sqlite3.Connection, key: str, subkeys: bool,
                  create: bool) -> int:
        c = conn.execute(
            "SELECT key_id, type FROM keys WHERE namespace=? AND key=?",
            (self.namespace, key))
        row = c.fetchone()
        if row:
            key_id, found_type = row[0], row[1]
            if found_type == "KV" and subkeys:
                raise TypeError(f"Key '{key}' does not use subkeys.")
            elif found_type == "KKV" and not subkeys:
                raise TypeError(f"Key '{key}' uses subkeys.")
        else:
            if create:
                c = conn.execute(
                    "INSERT INTO keys (namespace, key, type) VALUES(?, ?, ?)",
                    (self.namespace, key, "KKV" if subkeys else "KV"))
                key_id = c.lastrowid
            else:
                raise KeyError(key)
        return key_id

    def unset(self, key: str, subkey: Optional[str] = None) -> None:
        if subkey is not None:
            with self.conn:
                try:
                    key_id = self._find_key(self.conn, key, subkeys=True,
                                            create=False)
                except KeyError:
                    return
                self.conn.execute(
                    "DELETE FROM key_subkey_values WHERE key_id=? AND subkey=?",
                    (key_id, subkey))
        else:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM keys WHERE namespace=? AND key=?",
                    (self.namespace, key))

    def exists(self, key: str, subkey: Optional[str] = None) -> bool:
        if subkey is not None:
            try:
                _ = self.get(key, subkey)
                return True
            except TypeError:
                raise
            except KeyError:
                return False
        else:
            c = self.conn.execute(
                "SELECT * FROM keys WHERE namespace=? AND key=?",
                (self.namespace, key))
        return c.fetchone() is not None

    def clear_all(self, except_keys: Optional[List[str]] = None) -> None:
        with self.conn:
            if except_keys:
                qmarks = ",".join("?" for _ in except_keys)
                self.conn.execute("DELETE FROM keys WHERE namespace=? "
                                  f"AND key NOT IN ({qmarks})",
                                  (self.namespace,) + tuple(except_keys))
            else:
                self.conn.execute("DELETE FROM keys WHERE namespace=?",
                                  (self.namespace,))

    def get_all_values(self) -> Dict[str, str]:
        c = self.conn.execute(
            "SELECT key, value FROM keys INNER JOIN key_values "
            "ON keys.key_id = key_values.key_id WHERE namespace=?",
            (self.namespace,))
        return {key: value for key, value in c}

    def get_all_dicts(self) -> Dict[str, Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}
        c = self.conn.execute(
            "SELECT key, subkey, value FROM keys LEFT JOIN key_subkey_values "
            "ON keys.key_id = key_subkey_values.key_id "
            "WHERE namespace=? AND type='KKV'", (self.namespace,))
        for key, subkey, value in c:
            result.setdefault(key, {})
            if value is None:
                continue
            result[key][subkey] = value
        return result
