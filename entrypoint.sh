#!/bin/bash
set -e

_term() {
    echo "Caught SIGTERM, shutting down..."
    kill -TERM "$child" 2>/dev/null
    wait "$child" 2>/dev/null
}

trap _term SIGTERM SIGINT

NETWORK_NAME="${NETWORK_NAME:-sandbox}"

if [ ! -f /etc/indy/indy_config.py ]; then
    echo "Creating default indy_config.py..."
    cat > /etc/indy/indy_config.py <<EOF
NETWORK_NAME = "${NETWORK_NAME}"
EOF
fi

mkdir -p "/var/lib/indy/${NETWORK_NAME}/data/${NODE_NAME}"
mkdir -p "/var/lib/indy/${NETWORK_NAME}/keys"
mkdir -p "/var/log/indy/${NETWORK_NAME}"

chown -R indy:indy /var/lib/indy /etc/indy /var/log/indy 2>/dev/null || true

: "${NODE_NAME:?NODE_NAME is required}"
: "${NODE_IP:?NODE_IP is required}"
: "${NODE_PORT:?NODE_PORT is required}"
: "${CLIENT_IP:?CLIENT_IP is required}"
: "${CLIENT_PORT:?CLIENT_PORT is required}"

exec start_indy_node "$NODE_NAME" "$NODE_IP" "$NODE_PORT" "$CLIENT_IP" "$CLIENT_PORT"
