from __future__ import annotations

from typing import Any

import aiohttp
import structlog

from bot.config import settings

log = structlog.get_logger()


class RemnawaveClient:
    """Async HTTP client for the Remnawave panel API."""

    def __init__(self) -> None:
        self._base_url = settings.remnawave_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.remnawave_api_token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, params=params, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.json()
                log.warning("remnawave_api_error", status=resp.status, url=url)
                return None

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict | None:
        """Return user dict from Remnawave if telegram_id matches, else None."""
        log.info("remnawave_get_user_by_telegram_id", telegram_id=telegram_id)
        result = await self._get("/api/users")
        log.info(
            "remnawave_api_response",
            result_keys=result.keys() if isinstance(result, dict) else None,
        )
        if result is None:
            return None
        # Remnawave returns {"response": {"total": N, "users": [...]}}
        if isinstance(result, dict):
            users = result.get("response", {}).get("users", [])
            if isinstance(users, list):
                for u in users:
                    if u.get("telegramId") == telegram_id:
                        return u
        return None

    async def get_user_stats(self, uuid: str) -> dict | None:
        """Return traffic/expiry stats for a user by their Remnawave UUID."""
        return await self._get(f"/api/users/{uuid}")

    async def get_user_services(self, uuid: str) -> list[dict]:
        """Return list of active subscription configs for a user."""
        result = await self._get(f"/api/users/{uuid}/subscription-info")
        if result is None:
            return []
        if isinstance(result, dict):
            return result.get("response", {}).get("items", [])
        return []


# Singleton instance
remnawave = RemnawaveClient()
