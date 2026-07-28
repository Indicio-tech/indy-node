# Migration Guide: Debian Package to Docker Deployment

This guide walks through migrating an existing indy-node from a Debian package (`.deb`) installation to Docker-based deployment.

---

## Prerequisites

- A running indy-node (existing .deb installation)
- SSH access to the node host
- `sudo` access
- Existing node keys and configuration

---

## Step 1: Install Docker Engine

Install Docker on the host following the [official Docker Engine installation guide](https://docs.docker.com/engine/install/ubuntu/).

Quick install for Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Verify installation:

```bash
sudo docker run hello-world
```

---

## Step 2: Copy Ledger Data to Docker Volumes

Stop the running indy-node service:

```bash
sudo systemctl stop indy-node
```

Create Docker volumes and copy existing data:

```bash
sudo docker volume create indy-data
sudo docker volume create indy-config
sudo docker volume create indy-logs
```

Copy data from the existing installation paths into the volumes. Docker volumes are stored under `/var/lib/docker/volumes/`.

```bash
# Copy ledger data
sudo cp -a /var/lib/indy/. /var/lib/docker/volumes/indy-data/_data/

# Copy configuration
sudo cp -a /etc/indy/. /var/lib/docker/volumes/indy-config/_data/

# Copy logs history (optional)
sudo cp -a /var/log/indy/. /var/lib/docker/volumes/indy-logs/_data/
```

Set correct ownership for the `indy` user (UID 1000) inside the container:

```bash
sudo chown -R 1000:1000 /var/lib/docker/volumes/indy-data/_data/
sudo chown -R 1000:1000 /var/lib/docker/volumes/indy-config/_data/
sudo chown -R 1000:1000 /var/lib/docker/volumes/indy-logs/_data/
```

---

## Step 3: Configure `docker-compose.yaml`

Create `docker-compose.yaml` on the host (e.g., at `/opt/indy-node/docker-compose.yaml`):

```yaml
services:
  indy-node:
    image: ghcr.io/hyperledger/indy-node:latest
    ports:
      - "${NODE_IP}:${NODE_PORT}:${NODE_PORT}"
      - "${CLIENT_IP}:${CLIENT_PORT}:${CLIENT_PORT}"
    volumes:
      - indy-data:/var/lib/indy
      - indy-config:/etc/indy
      - indy-logs:/var/log/indy
    environment:
      - NODE_NAME=<your-node-name>
      - NODE_IP=<your-node-ip>
      - NODE_PORT=<your-node-port>
      - CLIENT_IP=<your-client-ip>
      - CLIENT_PORT=<your-client-port>
      - NETWORK_NAME=<your-network-name>
      - BIND_IP=0.0.0.0
    restart: unless-stopped

volumes:
  indy-data:
    external: true
  indy-config:
    external: true
  indy-logs:
    external: true
```

Replace the environment variables with your node's existing values from:
- `/etc/indy/indy_config.py` — contains `NETWORK_NAME`
- Node configuration (usually from the initial setup or `pool_config.py`)

The `external: true` on volumes tells Docker Compose to use the volumes you created in Step 2 rather than creating new ones.

---

## Step 4: Test Container Run

Start the container:

```bash
sudo docker compose -f /opt/indy-node/docker-compose.yaml up -d
```

Check the logs:

```bash
sudo docker compose -f /opt/indy-node/docker-compose.yaml logs -f
```

Verify the node connects to the pool:

```bash
sudo docker compose -f /opt/indy-node/docker-compose.yaml exec indy-node cat /var/log/indy/<network-name>/node.log | tail -50
```

If the container starts successfully and the node connects to the pool, stop it for the next step:

```bash
sudo docker compose -f /opt/indy-node/docker-compose.yaml down
```

---

## Step 5: Switch systemd Service to Control Docker Container

Create a systemd service file at `/etc/systemd/system/indy-node.service`:

```ini
[Unit]
Description=Indy Node (Docker)
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/docker compose -f /opt/indy-node/docker-compose.yaml down
ExecStart=/usr/bin/docker compose -f /opt/indy-node/docker-compose.yaml up
ExecStop=/usr/bin/docker compose -f /opt/indy-node/docker-compose.yaml down
WorkingDirectory=/opt/indy-node

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable indy-node
sudo systemctl start indy-node
```

Verify the service status:

```bash
sudo systemctl status indy-node
```

---

## Rollback

### Rollback to Debian Package

If you need to revert to the Debian package installation:

1. Stop and disable the Docker systemd service:
   ```bash
   sudo systemctl stop indy-node
   sudo systemctl disable indy-node
   ```

2. Reinstall the original .deb package and restart:
   ```bash
   sudo apt-get install --reinstall indy-node
   sudo systemctl start indy-node
   ```

### Automatic Rollback on Upgrade Failure

When an upgrade via `POOL_UPGRADE` with the `image` field is performed, the node automatically:

1. **Saves the current image** before pulling the new one (tagged as `indy-node-rollback`).
2. **Pulls the new image** and recreates the container.
3. **Performs a health check** by polling `docker inspect` for container state `running`.
4. **If the health check fails** within the timeout (default 30s), the node automatically:
   - Re-tags the rollback image to the original image reference.
   - Restarts the container with `docker compose up -d --force-recreate`.
   - Logs the rollback as a failed upgrade.
5. **If the rollback also fails**, a critical error is logged for manual intervention.

The rollback image tag (`indy-node-rollback`) persists locally on the host. To manually trigger a rollback to the previously saved image:

```bash
docker tag indy-node-rollback ghcr.io/hyperledger/indy-node:latest
docker compose -f /opt/indy-node/docker-compose.yaml up -d --force-recreate indy-node
```

---

## Upgrading

Once migrated, upgrades are handled via `POOL_UPGRADE` with the `image` field. The node automatically:

1. Verifies Docker daemon availability.
2. Saves the current image for rollback.
3. Pulls the new Docker image.
4. Restarts the container with `docker compose up -d --force-recreate`.
5. Polls the container state until it reaches `running`.
6. On health check failure, automatically rolls back to the previous image.

The underlying operations are equivalent to:

```bash
docker info
docker tag $(docker inspect --format '{{.Image}}' indy-node) indy-node-rollback
docker compose pull indy-node
docker compose up -d --force-recreate indy-node
# Health check: poll docker inspect --format '{{.State.Status}}' indy-node for "running"
```

This replaces the old `apt-get upgrade` / `dpkg -i` process.
