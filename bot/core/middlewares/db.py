from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Callable, Awaitable

from bot.db.engine import AsyncSessionFactory


class DbSessionMiddleware(BaseMiddleware):
    """Inject an async DB session into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionFactory() as session:
            data["session"] = session
            return await handler(event, data)
