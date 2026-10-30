#!/usr/bin/env python3
"""Fake Cloud Run deploy, verify, promote with immutable image ID handoff.

NO GCP API calls: it only creates and validates local JSON artifacts.
"""
import json
import os
import pathlib
import sys
from typing import Any


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing required artifact: {path}")
    return json.loads(path.read_text())


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value, indent=2))


def run(action: str, service: str) -> pathlib.Path:
    if service not in {"payment-service", "notification-service"}:
        raise SystemExit("Unknown mock service")
    base = pathlib.Path('.artifacts') / service
    sha = os.getenv('GITHUB_SHA', 'local')
    pipeline = os.getenv('GITHUB_RUN_ID', 'local')

    if action == 'deploy':
        image_file = base / 'image-id.txt'
        if not image_file.is_file():
            raise SystemExit('Missing tested image-id artifact')
        image_id = image_file.read_text().strip()
        if not image_id.startswith('sha256:'):
            raise SystemExit('Expected real Docker image ID (sha256:...)')
        candidate = {
            'service': service,
            'revision': f'{service}-candidate-{pipeline}',
            'commit': sha,
            'image_id': image_id,
            'traffic_percent': 0,
            'backend': 'MOCK_ONLY',
        }
        write_json(base / 'candidate.json', candidate)
        return base / 'candidate.json'

    candidate = read_json(base / 'candidate.json')
    if candidate['service'] != service or candidate['commit'] != sha:
        raise SystemExit('Candidate does not match requested service/commit')
    if candidate['traffic_percent'] != 0 or candidate['backend'] != 'MOCK_ONLY':
        raise SystemExit('Unsafe or invalid candidate')
    if action == 'smoke':
        smoke = {'revision': candidate['revision'], 'image_id': candidate['image_id'],
                 'passed': True, 'checks': ['readiness', 'route_contract', 'image_identity']}
        write_json(base / 'smoke.json', smoke)
        return base / 'smoke.json'
    if action == 'promote':
        smoke = read_json(base / 'smoke.json')
        if not smoke.get('passed') or smoke['revision'] != candidate['revision'] or smoke['image_id'] != candidate['image_id']:
            raise SystemExit('Cannot promote an unverified image/revision')
        release = {**candidate, 'traffic_percent': 100, 'smoke_passed': True}
        write_json(base / 'release.json', release)
        return base / 'release.json'
    raise SystemExit('Usage: mock_cloud_run.py deploy|smoke|promote SERVICE')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: mock_cloud_run.py deploy|smoke|promote SERVICE')
    run(sys.argv[1], sys.argv[2])
