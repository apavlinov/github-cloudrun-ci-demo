"""Static and mock-run verification; can be executed before pushing to GitHub."""
import fnmatch
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_yaml(path):
    try:
        import yaml
    except ImportError:
        raise unittest.SkipTest('pip install pyyaml for workflow checks')
    return yaml.safe_load((ROOT / path).read_text())


def flatten(items):
    for item in items:
        if isinstance(item, list):
            yield from flatten(item)
        else:
            yield item


def matched_filters(files):
    filters = load_yaml('.github/path-filters.yml')
    return {name for name, globs in filters.items()
            if any(fnmatch.fnmatch(f, g) for f in files for g in flatten(globs))}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.jobs = load_yaml('.github/workflows/ci.yml')['jobs']

    def test_apply_is_gated_and_serialized(self):
        apply = self.jobs['terraform_apply']
        self.assertEqual(apply['environment'], 'staging-infra')
        self.assertEqual(apply['concurrency'], {'group': 'staging-infra', 'cancel-in-progress': False})
        self.assertIn("github.event_name == 'push'", apply['if'])
        self.assertIn('infra_code', apply['if'])

    def test_infra_ready_rejects_failed_plan(self):
        condition = self.jobs['infra_ready']['if']
        self.assertIn('!cancelled()', condition)
        self.assertIn("needs.terraform_plan.result != 'failure'", condition)
        self.assertIn('needs.terraform_apply.result', condition)

    def test_releases_wait_for_infra_and_hold_one_lock(self):
        for service in ['payment', 'notification']:
            job = self.jobs[f'release_{service}']
            self.assertIn('infra_ready', job['needs'])
            self.assertIn(f'ci_{service}', job['needs'])
            self.assertIn("needs.infra_ready.result == 'success'", job['if'])
            self.assertEqual(job['concurrency']['group'], f'staging-{service}-service')
            self.assertFalse(job['concurrency']['cancel-in-progress'])
            self.assertEqual(job['uses'], './.github/workflows/release-service.yml')

    def test_ci_ok_covers_every_pr_job(self):
        pr_jobs = {name for name, job in self.jobs.items()
                   if name != 'ci_ok' and "github.event_name == 'push'" not in job.get('if', '')}
        self.assertEqual(set(self.jobs['ci_ok']['needs']), pr_jobs)
        self.assertEqual(self.jobs['ci_ok']['if'], 'always()')

    def test_promote_is_the_deployment(self):
        release = load_yaml('.github/workflows/release-service.yml')['jobs']
        self.assertEqual(release['promote']['environment'], '${{ inputs.environment }}')
        self.assertNotIn('environment', release['deploy'])
        self.assertEqual(release['promote']['needs'], 'smoke')


class ChangeMatrixTests(unittest.TestCase):
    def test_matrix(self):
        scenarios = [
            (['services/payment-service/server.py'], {'payment'}),
            (['services/notification-service/server.py'], {'notification'}),
            (['shared/contracts.py'], {'common', 'payment', 'notification'}),
            (['infra/staging/main.tf'], {'infra', 'infra_code'}),
            (['services/payment-service/server.py', 'infra/staging/main.tf'], {'payment', 'infra', 'infra_code'}),
            (['.github/workflows/ci.yml'], {'common', 'payment', 'notification', 'infra', 'pipeline'}),
            (['tests/test_pipeline.py'], {'pipeline'}),
            (['README.md'], set()),
        ]
        for files, expected in scenarios:
            with self.subTest(files=files):
                self.assertEqual(matched_filters(files), expected)


class MockReleaseTests(unittest.TestCase):
    def test_mock_promotion_requires_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp) / '.artifacts/payment-service'
            base.mkdir(parents=True)
            (base / 'image-id.txt').write_text('sha256:' + 'f' * 64)
            env = {**os.environ, 'GITHUB_SHA': 'test-sha', 'GITHUB_RUN_ID': '77'}
            cmd = [sys.executable, str(ROOT / 'scripts/mock_cloud_run.py')]

            def call(action):
                return subprocess.run([*cmd, action, 'payment-service'], cwd=tmp, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(call('deploy').returncode, 0)
            self.assertNotEqual(call('promote').returncode, 0)
            self.assertEqual(call('smoke').returncode, 0)
            self.assertEqual(call('promote').returncode, 0)
            release = json.loads((base / 'release.json').read_text())
            self.assertEqual(release['traffic_percent'], 100)
            self.assertEqual(release['image_id'], 'sha256:' + 'f' * 64)

    def test_app_contract(self):
        self.assertTrue((ROOT / 'services/payment-service/Dockerfile').exists())
        self.assertTrue((ROOT / 'services/notification-service/Dockerfile').exists())


if __name__ == '__main__':
    unittest.main()
