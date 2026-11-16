# infra/CLAUDE.md — AISV-Team17

Also follow the root `CLAUDE.md`. If a rule below conflicts with the root file, follow this file.

## 1. What infra/ contains

`infra/` holds configuration files for Grafana, OTel Collector, and Prometheus only. It does **not** contain `docker-compose.yml` — the Compose files live at the repository root.

| Path | Purpose |
| --- | --- |
| `infra/grafana/dashboards/` | Grafana dashboard JSON and provisioning YAML |
| `infra/otel-collector/config.yaml` | OTel Collector pipeline config |
| `infra/prometheus/prometheus.yml` | Prometheus scrape config |

## 2. Compose files (repository root)

`docker-compose.yml` and `docker-compose.override.yml` live at the repository root, not in `infra/`.

- `docker-compose.yml` — all services, production-ready
- `docker-compose.override.yml` — local-only overrides (extra port exposure for development)

Changes to `docker-compose.yml` require approval from both parts before committing (CODEOWNERS).

## 3. Memory limits

Every service in `docker-compose.yml` must declare `mem_limit`. Do not add a service without one. Refer to `docs/ops/docker.md` for the current allocation table and the reasoning behind each value.

## 4. Image tags

- Use SHA tags only: `sha-<short-commit>`. Never use `latest` or branch-name tags in any Compose file (ADR-019).
- GHCR image names follow: `ghcr.io/driftsight-lab/driftsight/<service>:<sha-tag>`.

## 5. Environment variables

- Commit `.env.example` only. Never commit `.env`.
- Secrets are injected by GitHub Actions CD via SCP from GitHub Secrets (ADR-021). Do not add secrets to any tracked file.
- For variable names and descriptions, see `docs/ops/env-setup.md`.

## 6. Ports

Follow the port table in `docs/ops/docker.md`. If a port needs to change, update that document in the same commit.

## 7. Change procedure

1. State the change and its reason before editing.
2. For `docker-compose.yml` changes, get approval from both parts before committing.
3. Update `docs/ops/docker.md` or `docs/ops/env-setup.md` in the same commit if the change affects their content.

---

end.