"""Authentification API pour le backend Vigie.

Chaque route publique doit être protégée par la dépendance ``require_api_key``.
Le secret partagé est fourni via la variable d'environnement ``VIGIE_API_KEY``
(entête HTTP ``X-API-Key`` ou ``Authorization: Bearer <token>``).

Si aucune clé n'est configurée, toutes les requêtes sont rejetées : c'est
volontaire pour éviter tout démarrage silencieux sans authentification.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def _expected_key() -> str:
    return os.getenv("VIGIE_API_KEY", "").strip()


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    expected = _expected_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VIGIE_API_KEY n'est pas configuré côté serveur.",
        )

    provided = x_api_key or ""
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()

    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API manquante ou invalide.",
        )
