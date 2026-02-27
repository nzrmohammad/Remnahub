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

    async def _post(self, path: str, data: dict | None = None) -> Any:
        url = f"{self._base_url}{path}"
        log.info("remnawave_post_request", url=url, data=data)
        async with aiohttp.ClientSession(headers=self._headers, timeout=self._timeout) as session:
            async with session.post(url, json=data, ssl=False) as resp:
                log.info("remnawave_post_response", status=resp.status, url=url)
                if resp.status in (200, 201):
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

    async def get_all_users_by_telegram_id(self, telegram_id: int) -> list[dict]:
        """Return all user dicts from Remnawave matching the telegram_id."""
        log.info("remnawave_get_all_users_by_telegram_id", telegram_id=telegram_id)
        result = await self._get(f"/api/users/by-telegram-id/{telegram_id}")
        if result is None:
            log.info("users_not_found", telegram_id=telegram_id)
            return []
        response_data = result.get("response")
        if isinstance(response_data, list):
            log.info("users_found", count=len(response_data))
            return response_data
        if isinstance(response_data, dict):
            return [response_data]
        return []

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

    async def get_all_users(
        self, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict] | None, int]:
        """Return paginated users from RemnaWave panel or None on error."""
        params = {"start": (page - 1) * per_page, "size": per_page}
        result = await self._get("/api/users", params=params)
        if result is None:
            return None, 0

        response_data = result.get("response", {})
        users = response_data.get("users", [])
        total = response_data.get("total", 0)
        if isinstance(users, list):
            return users, total
        return [], 0


# Singleton instance
remnawave = RemnawaveClient()


async def get_internal_squads() -> list[dict]:
    """Return list of internal squads from RemnaWave panel."""
    try:
        result = await remnawave._get("/api/internal-squads")
        if result is None:
            log.warning("get_internal_squads returned None")
            return []
        response = result.get("response")
        if response is None:
            log.warning("get_internal_squads response is None")
            return []
        squads = response if isinstance(response, list) else []
        log.info("get_internal_squads", count=len(squads))
        return squads
    except Exception as e:
        log.error("get_internal_squads_error", error=str(e))
        return []


async def create_remnawave_user(
    username: str,
    telegram_id: int | None,
    traffic_limit_bytes: int,
    expire_at: str,
    traffic_reset: str = "NO_RESET",
    squads: list[str] | None = None,
) -> dict | None:
    """Create a new user in RemnaWave panel."""
    data = {
        "username": username,
        "status": "ACTIVE",
        "trafficLimitBytes": traffic_limit_bytes,
        "trafficLimitStrategy": traffic_reset,
        "expireAt": expire_at,
    }
    if telegram_id:
        data["telegramId"] = telegram_id
    if squads:
        data["activeInternalSquads"] = squads

    result = await remnawave._post("/api/users", data)
    if result:
        return result.get("response")
    return None


async def revoke_user_subscription(uuid: str) -> dict | None:
    """Revoke user subscription and generate new short UUID."""
    data = {"revokeOnlyPasswords": False}
    result = await remnawave._post(f"/api/users/{uuid}/actions/revoke", data)
    if result:
        return result.get("response")
    return None


async def reset_and_set_user_package(
    uuid: str,
    volume_bytes: int,
    expire_at: str,
) -> dict | None:
    """Reset user traffic to 0 and set new volume and expiry."""
    data = {
        "trafficLimitBytes": volume_bytes,
        "trafficLimitStrategy": "RESET",
        "expireAt": expire_at,
        "usedTrafficBytes": 0,
    }
    result = await remnawave._post(f"/api/users/{uuid}", data)
    if result:
        return result.get("response")
    return None
