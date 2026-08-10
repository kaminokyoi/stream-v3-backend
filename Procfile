web: uv run gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120
worker: uv run celery -A config worker -l info
beat: uv run celery -A config beat -l info
migrate: uv run manage.py migrate --noinput