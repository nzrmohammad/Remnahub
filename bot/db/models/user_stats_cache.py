from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class UserStatsCache(Base):
    __tablename__ = "user_stats_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    used_traffic_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_traffic_bytes: Mapped[int] = mapped_column(Integer, default=0)
    remaining_traffic_bytes: Mapped[int] = mapped_column(Integer, default=0)
    expire_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    online_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<UserStatsCache uuid={self.uuid} status={self.status}>"
