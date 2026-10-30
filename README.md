# GitHub Actions demo: PR → main → Terraform approval → mock Cloud Run

**Safe demo:** 2 Python services, *real* Docker builds + container checks, *real* local
Terraform plan/apply using built-in `terraform_data`, and a **MOCK Cloud Run** release.
No GCP credentials, no `gcloud`, no Artifact Registry, no real traffic changes.

GitHub port of the GitLab demo: same services, scripts and scenarios, built from
GitHub-native pieces (path filters, environments, concurrency, reusable workflows).

## Workflows

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | Entry point for `pull_request` and `push` to `main`: change detection, CI, Terraform plan/apply, release |
| `.github/workflows/service-ci.yml` | Reusable: syntax → unit → Docker build → running-container checks for one service |
| `.github/workflows/release-service.yml` | Reusable: mock deploy (0%) → smoke → promote (100%) of the tested image |
| `.github/path-filters.yml` | Which paths trigger which jobs (used by `dorny/paths-filter` and `tests/`) |
| `.github/dependabot.yml` | Weekly updates for SHA-pinned actions and service base images |

## What is tested

- **PR:** syntax, unit tests, Docker build, running container `/health` and `/version`;
  Terraform fmt/init/validate/plan if `infra/**` changes, with the plan posted as a
  sticky PR comment and in the job summary. No deploy, no apply.
- **main:** rebuild and verify the merge commit's images; `terraform_apply` waits for
  approval on the `staging-infra` environment if infra changed; then mock
  deploy → smoke → promote of the *same* image ID.
- **Selective:** payment change → payment jobs only; notification → notification only;
  shared, scripts or workflow change → both; Terraform-only → plan/apply; docs → `ci_ok` only.
- **Self-test:** `actionlint` + `tests/` run when `.github/**`, `scripts/**` or `tests/**` change.

## Repository setup (one time)

1. Create the repository on GitHub and push `main`.
2. **Settings → Environments:**
   - `staging-infra`: add **Required reviewers** (and optionally *Prevent self-review*).
     This is what puts `terraform_apply` into *Waiting for review*. Without reviewers
     the apply runs immediately.
   - `staging`: optional; restrict *Deployment branches* to `main`.
   - Required reviewers work on public repositories on every plan; private repositories
     need a paid plan for them. Check GitHub's current plan matrix.
3. **Settings → Rules → Rulesets** for `main`: require a pull request, and require the
   status check **`ci_ok`** only. Do not require individual jobs: path-filtered jobs
   are skipped and `ci_ok` already aggregates them.
4. **Settings → Actions → General:** workflow permissions *Read repository contents*
   (each job raises only what it needs). Squash merge and merge commits both work.

## Scenarios

1. **A, payment only.** Branch from `main`, edit `services/payment-service/server.py`
   (e.g. the docstring), open a PR. Expect `ci_payment / build` and `ci_ok`; no
   notification, Terraform or release jobs. After merge: `ci_payment` →
   `infra_ready` → `release_payment / deploy`, `/ smoke`, `/ promote`.
2. **B, infrastructure only.** In `infra/staging/main.tf` change `default = "small"` to
   `default = "medium"`. The PR gets the Terraform plan comment. After merge the run
   shows **Waiting** at `terraform_apply` until a reviewer approves it in the run page.
3. **C, code and infrastructure.** Change both files in one PR. After merge
   `release_payment` waits for `infra_ready`, which waits for the approved apply.

### Expected matrix

| Change | PR | main |
|---|---|---|
| `services/payment-service/**` | `ci_payment` | `ci_payment` → `release_payment` |
| `services/notification-service/**` | `ci_notification` | `ci_notification` → `release_notification` |
| `shared/**`, `scripts/**` | both services (+ selftest for `scripts/**`) | both services, both releases |
| `infra/**` | `terraform_plan` (+ PR comment) | plan → **approval** → apply → `infra_ready` |
| app + infra | both | release waits for the approved apply |
| `.github/workflows/**` | everything incl. plan + selftest | everything, **no apply** |
| `tests/**` | selftest | selftest |
| `README.md` | `ci_ok` only | `infra_ready` + `ci_ok` |

## Local checks

```sh
pip install pyyaml
python -m unittest discover -s tests -v
python -m unittest discover -s services/payment-service/tests -v
python -m unittest discover -s services/notification-service/tests -v
actionlint   # optional, if installed
```

## How it maps to the GitLab version

| GitLab | GitHub Actions here |
|---|---|
| `rules: changes:` per job | `changes` job (`dorny/paths-filter`) + `if:` on outputs |
| Manual `terraform_apply`, pipeline *Blocked* | `environment: staging-infra` with required reviewers, *Waiting* |
| `infra_ready` with `needs: optional: true` | `if: !cancelled()` + explicit `needs.*.result` checks |
| `resource_group` per job | `concurrency` on the caller job: the whole deploy → smoke → promote holds one lock |
| `environment: action: prepare/verify` | Only `promote` declares the environment, so only it is a deployment |
| `reports: terraform` widget | Sticky PR comment + job summary |
| Docker-in-Docker | Docker built into `ubuntu-latest` |
| "Pipelines must succeed" | Ruleset requiring the `ci_ok` check |
| `interruptible` | Workflow `concurrency` with `cancel-in-progress` on PRs |

## GitHub-specific pitfalls handled here

- **Skipped jobs cascade.** A skipped ancestor (e.g. `terraform_apply` when infra did not
  change) skips everything downstream unless the job uses a status function. Hence
  `!cancelled()` plus explicit result checks in `infra_ready` and `release_*`.
- **A failed plan skips apply.** A naive "apply succeeded or skipped" gate would pass;
  `infra_ready` also requires `terraform_plan` not to have failed.
- **Path filters vs required checks.** Workflow-level `on.paths` leaves required checks
  pending forever; filtering happens per job and `ci_ok` is the single required check.
- **Concurrency keeps one pending run.** A newer waiting release replaces an older
  waiting one: older releases are dropped, not queued (newest wins).
- **Artifacts are readable by anyone with read access.** The binary plan is uploaded
  only on `main` and only for 2 days. Real infra should keep plans in a private bucket.
- **Fork PRs have a read-only token and no secrets.** The plan comment is skipped for
  them; `pull_request_target` is deliberately not used.
- **Supply chain.** Every action is pinned to a commit SHA (version in a comment);
  Dependabot updates them.

## Important limits

- No image is pushed to a registry. `image-id.txt` is a **local Docker image ID**
  passed as an artifact, not an OCI manifest digest; artifacts expire after 2–7 days.
- `terraform_data` creates **no GCP resources** and uses **temporary local state**:
  every plan is "1 to add" and apply results are discarded.
- The mock smoke test checks artifact/revision identity; it does not call a live URL.
  Running-container `/health` and `/version` checks happen in `service-ci.yml`.

## Матрица изменений и развитие (staging / prod / frontend)

### Как работает сейчас

| Что изменилось | Application CI (PR и main) | Infrastructure CD | Application CD (только main) |
|---|---|---|---|
| `services/notification-service/**` | `ci_notification` | — | `release_notification` |
| `services/payment-service/**` | `ci_payment` | — | `release_payment` |
| `shared/**`, `scripts/**` | CI обоих сервисов | — | Release обоих сервисов |
| `infra/staging/**` | — | PR: plan (комментарий в PR); main: plan → **approval** → apply | — (только `infra_ready`) |
| Код + Terraform | CI изменённого сервиса | Как `infra/staging/**` | Release ждёт `infra_ready`, то есть одобренного apply |
| `services/frontend/**` | Сервиса пока нет: только `ci_ok` | — | — |
| `.github/workflows/**` | Всё + selftest | plan, **без apply** | Release обоих сервисов |
| `tests/**` | selftest | — | — |
| Документация | `ci_ok` | — | — |

### Целевая матрица: staging + prod + frontend

| Что изменилось | Application CI | Infrastructure CD | App CD: staging | App CD: prod |
|---|---|---|---|---|
| `services/<backend>/**` | build, test, verify, push в registry (digest) | — | Авто: deploy 0% → smoke → promote | Approval на environment `production`: promote **того же digest** |
| `services/frontend/**` | lint, unit, build бандла или образа | — | Авто: deploy → e2e (Playwright) против staging API | Approval: promote того же артефакта |
| `shared/**` | Build зависимых backend-сервисов | — | Release зависимых | Promote зависимых |
| `contracts/**` (OpenAPI/proto) | Зависимые backend + генерация клиента и сборка frontend + contract tests | — | Backend → затем frontend | В том же порядке |
| `infra/modules/**` | — | plan staging и prod; apply staging → apply prod | Ждёт `infra_ready_staging` | Ждёт `infra_ready_prod` |
| `infra/staging/**` | — | plan → approval → apply staging | Ждёт `infra_ready_staging` | Не затрагивается |
| `infra/prod/**` | — | PR: plan; main: approval → apply prod | Не затрагивается | Ждёт `infra_ready_prod` |
| `.github/workflows/**` | Всё + selftest | plan всех окружений | Release всех (проверка CI) | **Нет**: изменение CI не катит prod |

### Что заложить на будущее

- **Prod:** тот же `release-service.yml` с `environment: production`; у environment —
  required reviewers и deployment branches = `main`. Каждый сервис ждёт своего approval
  независимо.
- **Build once, promote digest:** push в GHCR или Artifact Registry в `service-ci.yml`;
  digest передаётся в release как input, а не artifact. Откат — re-run старого
  release-запуска с теми же inputs.
- **GCP:** `google-github-actions/auth` + `permissions: id-token: write`; service account
  каждого окружения доверяет только своему claim `environment` в OIDC-токене.
- **Infra по окружениям:** `infra/modules/`, `infra/staging/`, `infra/prod/`; remote
  state в GCS; отдельные `terraform_apply_*` и `infra_ready_*` на окружение. Plan-файлы
  хранить в приватном bucket, а не в artifacts.
- **Drift detection:** `drift.yml` с `on: schedule` и `terraform plan -detailed-exitcode`;
  отдельный workflow, поэтому deploy-джобы туда не попадают.
- **Frontend:** фильтр `frontend: [services/frontend/**, contracts/**]`, node-джоб с
  кэшем `actions/setup-node`, конфиг окружения в runtime (`config.json`), порядок
  `needs: release_<backend>` + `!cancelled()`.
- **Масштабирование:** `changes` отдаёт JSON-список сервисов → один matrix-джоб вызывает
  `service-ci.yml` и `release-service.yml`. Учтите: у matrix-джоба один общий `result`,
  поэтому падение CI одного сервиса блокирует release остальных — для независимости
  сервисов держите release внутри одного reusable workflow на сервис.
- **Merge queue + `on: merge_group`:** проверка merged result до попадания в `main`.
