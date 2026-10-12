"""
Upload d'images vers Supabase Storage (bucket 'preuves').
"""
import logging
import uuid
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def upload_image(file, prefix="img_"):
    """
    Upload une image vers le bucket Supabase 'preuves'.
    Retourne l'URL publique ou None en cas d'echec.
    """
    if not file or not file.filename:
        return None

    try:
        supabase_url = current_app.config["SUPABASE_URL"]
        service_key = current_app.config["SUPABASE_SERVICE_KEY"]

        # Nom de fichier unique
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
        if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
            ext = "png"
        filename = f"{prefix}{uuid.uuid4().hex}.{ext}"

        # Lecture du contenu
        file.seek(0)
        content = file.read()
        file.seek(0)

        # Content-type
        mime_map = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"
        }
        content_type = mime_map.get(ext, "image/png")

        # Upload vers Supabase Storage
        url = f"{supabase_url}/storage/v1/object/preuves/{filename}"
        headers = {
            "Authorization": f"Bearer {service_key}",
            "Content-Type": content_type,
            "x-upsert": "true",
        }

        r = requests.post(url, data=content, headers=headers)

        if r.status_code in (200, 201):
            public_url = f"{supabase_url}/storage/v1/object/public/preuves/{filename}"
            logger.info(f"Image uploadee: {public_url}")
            return public_url
        else:
            logger.error(f"upload_image echec: {r.status_code} - {r.text[:200]}")
            return None

    except Exception as e:
        logger.error(f"upload_image exception: {e}")
        return None