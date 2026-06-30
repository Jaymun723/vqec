# VQEC

Visualize Quantum Error Correction — server rewrite specification and legacy reference.

## Documentation

| Document | Description |
|---|---|
| [`architecture.md`](docs/architecture.md) | Target system design, state machines, repo layout |
| [`frontend_api_spec.md`](docs/frontend_api_spec.md) | Frontend / CLI integration guide |
| [`worker_api_spec.md`](docs/worker_api_spec.md) | Distributed worker integration guide |
| [`experiment_config_schema.md`](docs/experiment_config_schema.md) | Experiment submit / validate payloads |
| [`task_workflow.md`](docs/task_workflow.md) | End-to-end registry and task workflow |
| [`db.md`](docs/db.md) | Database schema, indexes, retention |
| [`operations.md`](docs/operations.md) | Environment variables, OpenAPI, deployment |
| [`server_api.md`](docs/server_api.md) | Legacy API reference + rewrite checklist |

**OpenAPI:** Not checked into the repo. The running server exposes `GET /openapi.json` and `/docs`, generated from Pydantic schemas in `src/vqec/server/models/schemas.py`.

## Legacy Code

The previous implementation lives in [`legacy-code/`](legacy-code/) for reference and test porting.

## Project Status

Specification phase — server implementation follows the target architecture in `architecture.md`.
