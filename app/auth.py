from fastapi import Header

from app.config import settings
from app.errors import AppError


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise AppError(
            code="unauthorized",
            message="Missing or invalid API key.",
            status_code=401,
        )
