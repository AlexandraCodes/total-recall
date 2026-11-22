#!/usr/bin/env bash
# Starts Flask (gunicorn) serving the API and the built React app. Builds the frontend if web/dist is missing.
set -e
if [ ! -f web/dist/index.html ]; then
  (cd web && npm install --no-audit --no-fund && npm run build)
fi
exec gunicorn -k gthread --workers 1 --threads 16 --timeout 180 -b 0.0.0.0:${PORT:-8000} server.app:app
