# Context Layer (Memory Layer) Plan and Implementation

## Goal

Build a unified context layer for the coding agent that supports:

1. Project structure analysis
2. Code AST extraction
3. Dependency graph
4. Historical interaction memory
5. Knowledge base retrieval (RAG)

## Data model (OceanBase)

Implemented tables:

- `project_files`: repository file tree snapshot and metadata
- `code_symbols`: extracted AST-level symbols (class/function)
- `dependency_edges`: import dependency relations
- `interaction_memories`: per-session dialogue memory
- `knowledge_chunks`: chunked retrieval units for code/doc text

## Execution plan (implemented)

1. Build index pipeline
- Scan workspace for supported file types
- Write project file metadata into `project_files`
- Extract symbols/dependencies into `code_symbols` and `dependency_edges`
- Chunk source text into `knowledge_chunks`

2. Build retrieval pipeline
- Parse query to keywords
- Retrieve recent dialogue memory from `interaction_memories`
- Retrieve related symbols/dependencies/chunks by keyword match
- Assemble a single context package for the `coder` agent

3. Integrate with generation flow
- On `/generate`: write user query memory
- Coder uses `RAGService` -> `ContextRetriever` to fetch context
- On completion: write assistant answer memory

4. Expose operation interfaces
- `POST /api/v1/context/index` for indexing
- `POST /api/v1/context/query` for retrieval inspection
- `POST /api/v1/memory/optimize` for manual compaction
- `POST /api/v1/project/init` for project graph/vector initialization
- `POST /api/v1/project/context` for project-scoped context retrieval
- `POST /api/v1/project/callers` for caller-file lookup

## Memory management optimization (implemented)

1. Dedup on write
- Every memory computes `content_hash`
- Same `(session_id, content_hash)` memory is not duplicated

2. Auto compaction
- When session memory count exceeds threshold, old memories are summarized
- A pinned `summary` memory is generated and detailed old items are removed

3. Retrieval scoring
- Memory: keyword overlap + importance + recency + summary bonus
- Knowledge chunk: keyword overlap + dependency graph source-file boost
- Final context is trimmed to char budget for token stability

## Implementation mapping

- Indexing logic: `backend/app/services/context_service.py` (`ContextIndexer`)
- Retrieval logic: `backend/app/services/context_service.py` (`ContextRetriever`)
- Persistence layer: `backend/app/repositories/context_repo.py`
- API routes: `backend/app/api/routes.py`
- SQL bootstrap: `sql/init_oceanbase.sql`
- CLI indexing: `scripts/build_context.py`

## Next improvements

1. Add embedding generation and vector retrieval for `knowledge_chunks`
2. Add weighted rerank across memory/symbol/dependency/chunk sources
3. Add incremental indexing by changed files (git diff aware)
4. Add memory summarization and TTL policy for long sessions
