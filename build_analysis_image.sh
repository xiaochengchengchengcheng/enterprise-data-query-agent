#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
docker build -f docker/Dockerfile.analysis -t enterprise-data-analyst-python:latest .
echo "Analysis image built: enterprise-data-analyst-python:latest"
