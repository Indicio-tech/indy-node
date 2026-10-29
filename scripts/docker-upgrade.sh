#!/bin/bash
set -e

UPGRADE_ENTRY="${1:-indy-node}"
COMPOSE_DIR="${2:-/opt/indy-node}"
HEALTH_TIMEOUT="${3:-30}"
ROLLBACK_TAG="indy-node-rollback"

echo "Checking Docker availability..."
docker info > /dev/null 2>&1 || { echo "ERROR: Docker is not available. Ensure Docker Engine is installed and running."; exit 1; }

echo "Saving current image for rollback..."
CURRENT_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$UPGRADE_ENTRY" 2>/dev/null || true)
CURRENT_DIGEST=$(docker inspect --format '{{.Image}}' "$UPGRADE_ENTRY" 2>/dev/null || true)
if [ -n "$CURRENT_DIGEST" ]; then
    docker tag "$CURRENT_DIGEST" "$ROLLBACK_TAG" 2>/dev/null || true
    echo "Saved current image $CURRENT_IMAGE as rollback target"
fi

echo "Pulling latest indy-node image..."
docker compose --project-directory "$COMPOSE_DIR" pull "$UPGRADE_ENTRY"

echo "Restarting container..."
docker compose --project-directory "$COMPOSE_DIR" up -d --force-recreate "$UPGRADE_ENTRY"

echo "Waiting for container to become healthy..."
end=$((SECONDS + HEALTH_TIMEOUT))
while [ $SECONDS -lt $end ]; do
    STATUS=$(docker inspect --format '{{.State.Status}}' "$UPGRADE_ENTRY" 2>/dev/null || echo "missing")
    if [ "$STATUS" = "running" ]; then
        echo "Container $UPGRADE_ENTRY is running"
        exit 0
    elif [ "$STATUS" = "created" ] || [ "$STATUS" = "restarting" ]; then
        sleep 2
    elif [ "$STATUS" = "missing" ]; then
        sleep 2
    else
        echo "ERROR: Container $UPGRADE_ENTRY is in unexpected state: $STATUS"
        break
    fi
done

echo "WARNING: Health check failed within ${HEALTH_TIMEOUT}s"

if [ -n "$CURRENT_IMAGE" ]; then
    echo "Attempting rollback to $CURRENT_IMAGE..."
    docker tag "$ROLLBACK_TAG" "$CURRENT_IMAGE" 2>/dev/null || true
    docker compose --project-directory "$COMPOSE_DIR" up -d --force-recreate "$UPGRADE_ENTRY"
    echo "Rollback initiated. Check container status with: docker compose --project-directory $COMPOSE_DIR ps"
else
    echo "ERROR: No rollback image available. Manual intervention required."
fi

exit 1
