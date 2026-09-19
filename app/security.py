from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.errors import AppError

PHOTO_URL_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours - plenty for a browsing session

# Reuses API_KEY as the HMAC secret for signed photo links. This is safe:
# itsdangerous signatures never reveal the secret, so handing out signed
# tokens carries no more risk than handing out the API key itself would.
_serializer = URLSafeTimedSerializer(settings.api_key, salt="design-matcher-photo")


def sign_photo_path(relative_path: str) -> str:
    return _serializer.dumps(relative_path)


def unsign_photo_token(token: str) -> str:
    try:
        return _serializer.loads(token, max_age=PHOTO_URL_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise AppError(code="link_expired", message="This image link has expired.", status_code=410)
    except BadSignature:
        raise AppError(code="invalid_token", message="This image link isn't valid.", status_code=404)


def build_photo_url(absolute_path: Path, *, catalog_root: Path) -> str:
    rel = absolute_path.resolve().relative_to(catalog_root.resolve())
    token = sign_photo_path(str(rel).replace("\\", "/"))
    return f"{settings.public_base_url.rstrip('/')}/api/v1/photos/{token}"
