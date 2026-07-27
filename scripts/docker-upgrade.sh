#!/bin/bash
set -e

# Pull the latest indy-node image and restart the container
docker compose pull indy-node
docker compose up -d --force-recreate indy-node
