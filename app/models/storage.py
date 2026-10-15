"""
Upload d'images vers Supabase Storage (bucket 'preuves').
SÉCURITÉ SÉVÈRE : validation magic bytes, Content-Type, taille, extension.
"""
import logging
import uuid
import requests
from flask import current_app

logger = logging.getLogger(__name__)

# ⚠️ SÉCURITÉ : limite de taille stricte (5 Mo)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Mo

# ⚠️ SÉCURITÉ : magic bytes (signature binaire reelle)
MAGIC_BYTES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpg',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
}

# ⚠️ SÉCURITÉ : extensions autorisees (liste blanche)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

# ⚠️ SÉCURITÉ : Content-Type autorises (liste blanche)
ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/jpg",
    "image/webp", "image/gif",
}

# Mapping extension → Content-Type
EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _valider_magic_bytes(content):
    """
    Verifie la signature binaire reelle du fichier.
    SÉCURITÉ : empeche les fichiers renommes (.exe → .png).
    """
    if not content or len(content) < 12:
        return None
    # PNG, JPG, GIF
    for magic, ext in MAGIC_BYTES.items():
        if content.startswith(magic):
            return ext
    # WebP : RIFF....WEBP
    if content[:4] == b'RIFF' and len(content) >= 12 and content[8:12] == b'WEBP':
        return 'webp'
    return None


def _extraire_extension(filename):
    """Extrait l'extension en minuscules d'un nom de fichier."""
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower().strip()
    return ext if ext else None


def _valider_content_type(content_type_http):
    """
    SÉCURITÉ : verifie le Content-Type HTTP envoye par le client.
    Empeche les uploads malveillants.
    """
    if not content_type_http:
        return True  # Pas de Content-Type → on validera par magic bytes
    ct = content_type_http.lower().strip()
    # Retire les parametres (ex: image/png;charset=utf-8)
    if ";" in ct:
        ct = ct.split(";")[0].strip()
    if not ct.startswith("image/"):
        logger.warning(f"Content-Type refuse (pas une image) : {ct}")
        return False
    if ct not in ALLOWED_CONTENT_TYPES:
        logger.warning(f"Content-Type non autorise : {ct}")
        return False
    return True


def upload_image(file, prefix="img_"):
    """
    Upload une image vers Supabase Storage (bucket 'preuves').
    
    SÉCURITÉ :
    - Verifie le Content-Type HTTP
    - Verifie l'extension (liste blanche)
    - Verifie la taille (max 5 Mo)
    - Verifie les magic bytes (signature reelle)
    - Renomme le fichier (evite les injections de chemin)
    - Content-Disposition pour eviter l'execution
    
    Retourne l'URL publique ou None en cas d'echec.
    """
    # ─── 1. Verification basique du fichier ───────────────────
    if not file or not file.filename:
        logger.warning("upload_image: fichier vide ou sans nom")
        return None

    # ─── 2. SÉCURITÉ : verifier le Content-Type HTTP ──────────
    content_type_http = getattr(file, "content_type", "") or ""
    if not _valider_content_type(content_type_http):
        return None

    # ─── 3. SÉCURITÉ : verifier l'extension (liste blanche) ──
    ext_declaree = _extraire_extension(file.filename)
    if not ext_declaree or ext_declaree not in ALLOWED_EXTENSIONS:
        logger.warning(f"upload_image: extension refusee ({ext_declaree}) - {file.filename}")
        return None

    # ─── 4. Lecture du contenu ────────────────────────────────
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

    # ─── 5. SÉCURITÉ : verifier la taille ─────────────────────
    if len(content) > MAX_FILE_SIZE:
        logger.warning(f"upload_image: fichier trop gros ({len(content)} octets)")
        return None

    if len(content) < 12:
        logger.warning("upload_image: fichier trop petit (magic bytes impossibles)")
        return None

    # ─── 6. SÉCURITÉ : verifier les magic bytes ───────────────
    ext_reelle = _valider_magic_bytes(content)
    if not ext_reelle:
        logger.warning(f"upload_image: magic bytes invalides - {file.filename}")
        return None

    # ─── 7. Determine l'extension finale (coherence) ──────────
    if ext_reelle == 'jpg' and ext_declaree in ('jpg', 'jpeg'):
        ext = ext_declaree
    elif ext_reelle == ext_declaree:
        ext = ext_reelle
    else:
        # L'extension declaree ne correspond pas a la reelle
        # → on utilise la reelle (plus sur)
        logger.warning(
            f"upload_image: extension declaree ({ext_declaree}) != reelle ({ext_reelle})"
        )
        ext = ext_reelle

    content_type = EXT_TO_MIME.get(ext, "image/png")

    # ─── 8. SÉCURITÉ : nom de fichier genere (anti-injection) ─
    # On ignore completement le nom original pour eviter :
    # - Les injections de chemin (../)
    # - Les caracteres speciaux
    # - Les doubles extensions (fichier.php.png)
    filename = f"{prefix}{uuid.uuid4().hex}.{ext}"

    # ─── 9. Envoi vers Supabase Storage ───────────────────────
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
            # ⚠️ SÉCURITÉ : Content-Disposition pour empecher l'execution
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=31536000, immutable",
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
            logger.info(f"Image uploadee : {filename}")
            return public_url
        else:
            status = r.status_code if r else "no-response"
            logger.error(f"upload_image echec : {status}")
            return None

    except Exception as e:
        logger.error(f"upload_image exception : {type(e).__name__}")
        return None


def supprimer_image(image_url):
    """
    Supprime une image du bucket Supabase.
    Utilise pour nettoyer les anciennes images (optionnel).
    """
    if not image_url or "preuves/" not in image_url:
        return False
    
    try:
        supabase_url = current_app.config.get("SUPABASE_URL", "").rstrip("/")
        service_key = current_app.config.get("SUPABASE_SERVICE_KEY", "")
        
        if not supabase_url or not service_key:
            return False
        
        # Extrait le nom du fichier de l'URL
        filename = image_url.split("preuves/")[-1].split("?")[0]
        
        # ⚠️ SÉCURITÉ : validation du nom de fichier
        if "/" in filename or ".." in filename:
            logger.warning(f"supprimer_image: nom invalide : {filename}")
            return False
        
        url = f"{supabase_url}/storage/v1/object/preuves/{filename}"
        headers = {"Authorization": f"Bearer {service_key}"}
        
        r = requests.delete(url, headers=headers, timeout=10)
        
        if r.status_code < 300:
            logger.info(f"Image supprimee : {filename}")
            return True
        return False
    except Exception as e:
        logger.error(f"supprimer_image : {type(e).__name__}")
        return False