"""GCS upload and signed URL helpers for meal photos."""

import io
import os
import uuid
from datetime import datetime, timedelta

from PIL import Image

MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 1200
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

MEAL_PHOTO_BUCKET = os.environ.get("MEAL_PHOTO_BUCKET", "jasondel-coach-data")
MEAL_PHOTO_PREFIX = os.environ.get("MEAL_PHOTO_PREFIX", "meals")

_storage_client = None


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage
        _storage_client = storage.Client()
    return _storage_client


def upload_meal_photo(
    image_bytes: bytes,
    mime_type: str,
    user_id: str = "athlete",
) -> tuple[str, bytes]:
    """Upload a meal photo to GCS after resizing.

    Returns:
        Tuple of (gcs_path, resized_jpeg_bytes) — the resized bytes are needed
        for passing to the agent for analysis.
    """
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {mime_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES)}")

    if len(image_bytes) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Image too large (max {MAX_IMAGE_SIZE_MB}MB)")

    # Resize to max 1200px longest edge
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

    # Convert to JPEG 85%
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    resized_bytes = buf.getvalue()

    # Build GCS path
    now = datetime.now()
    short_id = uuid.uuid4().hex[:6]
    blob_name = f"{MEAL_PHOTO_PREFIX}/{user_id}/{now.strftime('%Y%m%d_%H%M%S')}_{short_id}.jpg"
    gcs_path = f"gs://{MEAL_PHOTO_BUCKET}/{blob_name}"

    # Upload
    bucket = _get_storage_client().bucket(MEAL_PHOTO_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(resized_bytes, content_type="image/jpeg")

    return gcs_path, resized_bytes


def generate_photo_url(gcs_path: str, expiry_minutes: int = 60) -> str:
    """Generate a V4 signed URL for a meal photo.

    Args:
        gcs_path: Full GCS path (gs://bucket/path/to/photo.jpg).
        expiry_minutes: URL validity in minutes (default 60).

    Returns:
        HTTPS signed URL, or empty string if gcs_path is empty.
    """
    if not gcs_path:
        return ""

    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name, blob_name = parts[0], parts[1]

    bucket = _get_storage_client().bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiry_minutes),
        method="GET",
    )
