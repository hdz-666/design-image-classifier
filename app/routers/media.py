from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.catalog.fs import catalog_root, is_image_file
from app.errors import AppError
from app.security import unsign_photo_token

router = APIRouter()


@router.get("/api/v1/photos/{token}")
async def get_photo(token: str):
    rel_path = unsign_photo_token(token)
    root = catalog_root().resolve()
    full_path = (root / rel_path).resolve()

    if root != full_path and root not in full_path.parents:
        raise AppError(code="invalid_token", message="This image link isn't valid.", status_code=404)
    if not is_image_file(full_path):
        raise AppError(code="not_found", message="Photo not found.", status_code=404)

    return FileResponse(full_path)
