FROM python:3.13-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory
WORKDIR /app

# Install system dependencies (Required for building certain Python packages like psycopg2)
RUN apk add --no-cache gcc musl-dev postgresql-dev libffi-dev

# Install dependencies using the lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

# Copy the rest of the application code
COPY . .

# Port
EXPOSE 8000

# Grant execution permissions and set up entrypoint
RUN chmod +x entrypoint.sh

# Run the app
ENTRYPOINT ["/app/entrypoint.sh"]
