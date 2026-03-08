"""Async HTTP client for the dataToAi Agent Gateway API.

Usage::

    from datatoai import DataToAiClient

    async with DataToAiClient("http://localhost:8080", api_key="ak_...") as client:
        manifest = await client.discover()
        session_id = await client.create_session()
        result = await client.invoke("code.execute", {"code": "print(42)"}, session_id=session_id)
        print(result)
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx


class DataToAiClient:
    """Async client for the dataToAi Agent Gateway."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        bearer_token: str | None = None,
        timeout: float = 120.0,
    ):
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        elif bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

    async def __aenter__(self) -> DataToAiClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    async def discover(self) -> dict[str, Any]:
        """Fetch the agent capability manifest."""
        resp = await self._client.get("/agent-api/v1/.well-known/agent.json")
        resp.raise_for_status()
        return resp.json()

    async def list_skills(self, category: str | None = None) -> list[dict[str, Any]]:
        """List available skills."""
        params = {}
        if category:
            params["category"] = category
        resp = await self._client.get("/agent-api/v1/skills", params=params)
        resp.raise_for_status()
        return resp.json().get("skills", [])

    async def get_skill(self, skill_id: str) -> dict[str, Any]:
        """Get detailed skill manifest."""
        resp = await self._client.get(f"/agent-api/v1/skills/{skill_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    async def invoke(
        self,
        skill_id: str,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a skill synchronously."""
        resp = await self._client.post(
            f"/agent-api/v1/skills/{skill_id}/invoke",
            json={"params": params, "session_id": session_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def stream(
        self,
        skill_id: str,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Invoke a skill with SSE streaming, yielding parsed events."""
        async with self._client.stream(
            "POST",
            f"/agent-api/v1/skills/{skill_id}/stream",
            json={"params": params, "session_id": session_id},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    async def create_session(self) -> str:
        """Create a new session and return the session_id."""
        resp = await self._client.post("/agent-api/v1/sessions")
        resp.raise_for_status()
        return resp.json()["session_id"]

    # ------------------------------------------------------------------
    # Dataset operations
    # ------------------------------------------------------------------
    async def list_datasets(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List available datasets."""
        params = {}
        if session_id:
            params["session_id"] = session_id
        resp = await self._client.get("/agent-api/v1/datasets", params=params)
        resp.raise_for_status()
        return resp.json().get("datasets", [])

    async def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Get dataset metadata."""
        resp = await self._client.get(f"/agent-api/v1/datasets/{dataset_id}")
        resp.raise_for_status()
        return resp.json()

    async def upload_dataset(
        self,
        file_path: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Upload a dataset file via the data.upload skill."""
        import os
        filename = os.path.basename(file_path)
        return await self.invoke(
            "data.upload",
            {"file_path": file_path, "filename": filename},
            session_id=session_id,
        )
