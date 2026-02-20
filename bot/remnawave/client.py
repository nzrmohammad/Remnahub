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
        self._timeout = aiohttp.ClientTimeout(total=30)

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base_url}{path}"
        log.info("remnawave_request", url=url, params=params)
        async with aiohttp.ClientSession(headers=self._headers, timeout=self._timeout) as session:
            async with session.get(url, params=params, ssl=False) as resp:
                log.info("remnawave_response", status=resp.status, url=url)
                if resp.status == 200:
                    return await resp.json()
                log.warning("remnawave_api_error", status=resp.status, url=url)
                return None

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict | None:
        """Return user dict from Remnawave if telegram_id matches, else None."""
        log.info("remnawave_get_user_by_telegram_id", telegram_id=telegram_id)
        result = await self._get(f"/api/users/by-telegram-id/{telegram_id}")
        if result is None:
            log.info("user_not_found", telegram_id=telegram_id)
            return None
        response_data = result.get("response")
        if isinstance(response_data, list):
            if response_data:
                user = response_data[0]
                log.info("user_found", telegramId=user.get("telegramId"))
                return user
            log.info("user_not_found", telegram_id=telegram_id)
            return None
        user = response_data if isinstance(response_data, dict) else None
        if user:
            log.info("user_found", telegramId=user.get("telegramId"))
        else:
            log.info("user_not_found", telegram_id=telegram_id)
        return user

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
