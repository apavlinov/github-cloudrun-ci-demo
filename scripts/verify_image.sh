#!/bin/sh
set -eu
service="$1"
sha="${GITHUB_SHA:-local}"
tag="pipeline-demo/$service:$sha"
output=".artifacts/$service"
docker load -i "$output/image.tar"
actual="$(docker image inspect --format '{{.Id}}' "$tag")"
expected="$(cat "$output/image-id.txt")"
[ "$actual" = "$expected" ] || { echo 'Wrong image: build and test artifact differ' >&2; exit 1; }
cid="$(docker run -d "$tag")"
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
# Test the real running container, NOT just python syntax or Dockerfile presence.
docker exec -e "SERVICE_EXPECTED=$service" "$cid" python -c '
import json, os, time, urllib.request
for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as response:
            data = json.load(response)
        assert data == {"status": "ok", "service": os.environ["SERVICE_EXPECTED"]}
        with urllib.request.urlopen("http://127.0.0.1:8080/version", timeout=2) as response:
            version = json.load(response)
        assert version["commit"] == os.environ["GIT_SHA"]
        print("Container smoke tests passed", data, version)
        break
    except Exception as exc:
        if attempt == 29: raise
        time.sleep(1)
'
