from typing import Any

# shortcut: in-memory, restart par khaali + sirf 1 worker, multi-worker ke liye Redis
_store: dict[int, dict[int, dict[str, Any]]] = {}


def set_status(user_id: int, endpoint_id: int, payload: dict[str, Any]) -> None:
    _store.setdefault(user_id, {})[endpoint_id] = payload


def get_user_statuses(
    user_id: int,
) -> list[dict[str, Any]]:
    return list(_store.get(user_id, {}).values())


def remove(user_id: int, endpoint_id: int) -> None:
    user = _store.get(user_id)
    if user is None:
        return
    user.pop(endpoint_id, None)
    if not user:
        del _store[user_id]


def clear() -> None:
    _store.clear()
