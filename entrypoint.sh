#!/bin/sh
set -e

# Collect static files
uv run manage.py collectstatic --noinput

# Run migrations automatically before starting the web service
# (migrate service handles this separately in docker-compose)
uv run manage.py migrate --noinput

# CRUCIAL: This runs the "command" specified in docker-compose.yml
exec "$@"
