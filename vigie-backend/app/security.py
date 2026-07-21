"""Dépendances de sécurité communes aux routes HTTP de Vigie."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from .config import config


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    return value.strip() or None


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Protège les routes internes avec X-API-Key ou Authorization: Bearer.

    L'absence de VIGIE_API_KEY est traitée comme une mauvaise configuration et
    ferme l'accès, au lieu de laisser silencieusement les routes publiques.
    """
    expected = config.vigie_api_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VIGIE_API_KEY n'est pas configurée sur le backend.",
        )

    provided = (x_api_key or _bearer_token(authorization) or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide ou manquante.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def valid_whatsapp_signature(raw_body: bytes, signature: str | None) -> bool:
    """Valide X-Hub-Signature-256 envoyé par Meta pour le corps HTTP brut."""
    app_secret = config.whatsapp_app_secret.strip()
    if not app_secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(signature, expected)


def valid_m2s_signature(raw_body: bytes, signature: str | None) -> bool:
    """Valide la signature HMAC SHA-256 du webhook de statut M2S.

    Le format retenu est ``sha256=<hex>``. Le nom exact de l'en-tête devra être
    confirmé par M2S ; le routeur accepte provisoirement les deux noms documentés
    dans le guide du chantier 2.
    """
    webhook_secret = config.m2s_webhook_secret.strip()
    if not webhook_secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(signature, expected)
