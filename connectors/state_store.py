from __future__ import annotations

from typing import Any, Dict

from core.cache import valkey_client


async def load_state(connector_name: str) -> Dict[str, Any]:
    state = await valkey_client.get(f"connector:{connector_name}:state")
    return state or {}


async def save_state(connector_name: str, state: Dict[str, Any]) -> None:
    await valkey_client.set(f"connector:{connector_name}:state", state)
