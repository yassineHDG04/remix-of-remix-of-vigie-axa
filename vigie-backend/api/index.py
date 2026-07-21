"""Point d'entrée Vercel (serverless).

Vercel exécute ce fichier à chaque requête HTTP : il expose l'application
FastAPI sous le nom `app`. Vercel ne peut PAS faire tourner de boucle de fond,
donc en serverless on met ENGINE_AUTOSTART=false et un CRON EXTERNE appelle
POST /api/engine/tick (protégé par ENGINE_TICK_TOKEN).

Voir le guide PDF : "Déployer le backend".
"""
from app.main import app  # noqa: F401
