#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="coach-test-db"

# Remove any leftover test container
podman rm -f "$CONTAINER_NAME" > /dev/null 2>&1 || true

echo "Starting test database on port 5433..."
podman run -d --name "$CONTAINER_NAME" \
  -p 5433:5432 \
  -e POSTGRES_DB=coach_test \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=dev \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -v coach-test-data:/var/lib/postgresql/data \
  docker.io/library/postgres:16-alpine

# Wait for postgres to be ready
echo "Waiting for database to accept connections..."
until podman exec "$CONTAINER_NAME" pg_isready -U postgres > /dev/null 2>&1; do
  sleep 0.5
done
echo "Test database ready."

# Run integration tests against the test database
CYCLING_COACH_DATABASE_URL="postgresql://postgres:dev@localhost:5433/coach_test" \
  pytest tests/integration/ "$@"
EXIT_CODE=$?

echo "Stopping test database..."
podman rm -f "$CONTAINER_NAME" > /dev/null 2>&1
podman volume rm coach-test-data > /dev/null 2>&1 || true

exit $EXIT_CODE
