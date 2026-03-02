# Project-Wide Context Plan (Implemented)

## Objective

Make AI reason over the whole repository instead of single files by combining:

1. Structural graph (file/class/function/interface/config/doc)
2. Cross-file dependency/call edges
3. Project-level vector retrieval
4. Context trimming strategy (`current file > direct deps > indirect deps`)

## Implementation steps

1. Initialization pipeline
- Parse code/config/doc files
- AST extraction for symbols and inheritance
- Import/call relation extraction
- Persist graph nodes/edges and project vectors

2. Storage model (OceanBase)
- `project_graph_nodes`
- `project_graph_edges`
- `project_vectors`

3. Retrieval pipeline
- Query embedding + candidate vector retrieval
- Dependency-layer priority boosting
- Context budget control

4. API
- `POST /api/v1/project/init`
- `POST /api/v1/project/context`
- `POST /api/v1/project/callers`

## Code mapping

- Service: `backend/app/services/project_context_service.py`
- Repository: `backend/app/repositories/context_repo.py`
- API: `backend/app/api/routes.py`
- Schema: `backend/app/api/schemas.py`
- SQL: `sql/init_oceanbase.sql`, `sql/migrations/20260303_project_graph_vectors.sql`
- CLI: `scripts/build_project_context.py`

## Optimization strategy for large repositories

1. On-demand parsing
- Use `module_path` in `/project/init` to index only active module.

2. Cached project context
- Keep vectors and graph in DB; retrieval only scores candidate subset.

3. Context trimming
- Rank by similarity + dependency distance + current file priority.
- Hard trim by `MEMORY_CONTEXT_CHAR_BUDGET`.
