from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "model_name": settings.model_name,
        # Populated once indexing (phase 3) exists.
        "index_loaded": False,
        "device": None,
        "index_size": 0,
        "last_reindex_at": None,
    }
