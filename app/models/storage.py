"""
Upload d'images vers Supabase Storage (bucket 'preuves').
Validation stricte : magic bytes, taille, extension, MIME.
"""
import logging
import uuid
import requests
from flask import current_app

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024

MAGIC_BYTES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpg',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
}

EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def _valider_magic_bytes(content):
    """Vérifie la signature binaire réelle du fichier."""
    if not content or len(content) < 12:
        return None
    for magic, ext in MAGIC_BYTES.items():
        if content.startswith(magic):
            return ext
    if content[:4] == b'RIFF' and len(content) >= 12 and content[8:12] == b'WEBP':
        return 'webp'
    return None


def _extraire_extension(filename):
    """Extrait l'extension en minuscules d'un nom de fichier."""
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower().strip()
    return ext if ext else None


def upload_image(file, prefix="img_"):
    """
    Upload une image vers Supabase Storage (bucket 'preuves').
    Validation : taille, extension, magic bytes.
    Retourne l'URL publique ou None en cas d'echec.
    """
    if not file or not file.filename:
        logger.warning("upload_image: fichier vide ou sans nom")
        return None

    ext_declaree = _extraire_extension(file.filename)
    if not ext_declaree or ext_declaree not in ALLOWED_EXTENSIONS:
        logger.warning(f"upload_image: extension refusee ({ext_declaree}) - {file.filename}")
        return None

    try:
        file.seek(0)
        content = file.read()
        file.seek(0)
    except Exception as e:
        logger.error(f"upload_image: lecture impossible - {type(e).__name__}")
        return None

    if not content:
        logger.warning("upload_image: contenu vide")
        return None

    if len(content) > MAX_FILE_SIZE:
        logger.warning(f"upload_image: fichier trop gros ({len(content)} octets)")
        return None

    ext_reelle = _valider_magic_bytes(content)
    if not ext_reelle:
        logger.warning(f"upload_image: magic bytes invalides - {file.filename}")
        return None

    if ext_reelle == 'jpg' and ext_declaree in ('jpg', 'jpeg'):
        ext = ext_declaree
    elif ext_reelle == ext_declaree:
        ext = ext_reelle
    else:
        logger.warning(
            f"upload_image: extension declaree ({ext_declaree}) != reelle ({ext_reelle}) - {file.filename}"
        )
        ext = ext_reelle

    content_type = EXT_TO_MIME.get(ext, "image/png")
    filename = f"{prefix}{uuid.uuid4().hex}.{ext}"

    try:
        supabase_url = current_app.config.get("SUPABASE_URL", "").rstrip("/")
        service_key = current_app.config.get("SUPABASE_SERVICE_KEY", "")

        if not supabase_url or not service_key:
            logger.error("upload_image: config Supabase manquante")
            return None

        url = f"{supabase_url}/storage/v1/object/preuves/{filename}"
        headers = {
            "Authorization": f"Bearer {service_key}",
            "Content-Type": content_type,
            "x-upsert": "false",
        }

        r = None
        for tentative in range(2):
            try:
                r = requests.post(url, data=content, headers=headers, timeout=30)
                if r.status_code in (200, 201):
                    break
                if tentative == 0 and r.status_code >= 500:
                    logger.warning(f"upload_image: retry apres status {r.status_code}")
                    continue
                break
            except requests.Timeout:
                if tentative == 0:
                    logger.warning("upload_image: timeout, retry")
                    continue
                logger.error("upload_image: timeout definitif")
                return None

        if r and r.status_code in (200, 201):
            public_url = f"{supabase_url}/storage/v1/object/public/preuves/{filename}"
            logger.info(f"Image uploadee: {filename}")
            return public_url
        else:
            status = r.status_code if r else "no-response"
            logger.error(f"upload_image echec: {status}")
            return None

    except Exception as e:
        logger.error(f"upload_image exception: {type(e).__name__}")
        return None