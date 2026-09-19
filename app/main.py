from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_api_key
from app.config import settings
from app.errors import register_exception_handlers
from app.routers import browse, health, media

app = FastAPI(title="Design Matcher API", version="0.1.0")

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)

# Signed, time-limited photo URLs - no API key, so plain <img> tags work.
app.include_router(media.router)

app.include_router(
    browse.router,
    prefix="/api/v1",
    tags=["browse"],
    dependencies=[Depends(require_api_key)],
)
