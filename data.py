from typing import Dict, Any, Tuple

import bot

# TODO: In-memory version, to be replaced with sqlite or similar.

_db: Dict[Tuple[str, str], Any] = {}


def get(handler: bot.Handler, key: str, default: Any = None) -> Any:
    return _db.get((handler.__class__.__name__, key), default)


def set(handler: bot.Handler, key: str, value: Any) -> None:
    _db[handler.__class__.__name__, key] = value


def exists(handler: bot.Handler, key: str) -> bool:
    return (handler.__class__.__name__, key) in _db