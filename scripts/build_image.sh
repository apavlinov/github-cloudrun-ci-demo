#!/bin/sh
set -eu
service="$1"
sha="${GITHUB_SHA:-local}"
tag="pipeline-demo/$service:$sha"
output=".artifacts/$service"
mkdir -p "$output"
echo "BUILD once for commit $sha: $tag"
docker build --build-arg "GIT_SHA=$sha" -f "services/$service/Dockerfile" -t "$tag" .
docker image inspect --format '{{.Id}}' "$tag" > "$output/image-id.txt"
docker save "$tag" -o "$output/image.tar"
echo "Local Docker image ID: $(cat "$output/image-id.txt")"
echo 'This is NOT an Artifact Registry manifest digest; that will require a registry push.'
