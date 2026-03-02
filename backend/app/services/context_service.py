from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.models import CodeSymbolEntity, DependencyEdgeEntity, KnowledgeChunkEntity, ProjectFileEntity
from app.repositories.context_repo import ContextRepository


SUPPORTED_SUFFIX = {".py", ".ts", ".tsx", ".js", ".java", ".md", ".yaml", ".yml", ".json"}
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}")
IMPORT_PATTERN = re.compile(r"import\s+.*?from\s+[\"']([^\"']+)[\"']")
REQUIRE_PATTERN = re.compile(r"require\([\"']([^\"']+)[\"']\)")
FUNCTION_PATTERN = re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)")
CLASS_PATTERN = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class IndexStats:
    files: int = 0
    symbols: int = 0
    dependencies: int = 0
    chunks: int = 0


class ContextIndexer:
    def __init__(self, repo: ContextRepository):
        self.repo = repo

    def index_workspace(self, workspace: str, repo_name: str, branch_name: str) -> IndexStats:
        base = Path(workspace).resolve()
        if not base.exists():
            raise FileNotFoundError(f"workspace not found: {base}")

        stats = IndexStats()
        file_rows: list[ProjectFileEntity] = []
        symbol_rows: list[CodeSymbolEntity] = []
        dep_rows: list[DependencyEdgeEntity] = []
        chunk_rows: list[KnowledgeChunkEntity] = []

        self.repo.clear_repo_context(repo_name, branch_name)

        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SUPPORTED_SUFFIX:
                continue

            rel_path = str(path.relative_to(base))
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            file_rows.append(
                ProjectFileEntity(
                    repo_name=repo_name,
                    branch_name=branch_name,
                    file_path=rel_path,
                    file_type=path.suffix.lstrip(".") or "text",
                    file_size=path.stat().st_size,
                    depth=len(path.relative_to(base).parts),
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )
            stats.files += 1

            file_symbols, file_deps = self._extract_symbols_and_dependencies(
                content=content,
                suffix=path.suffix,
                repo_name=repo_name,
                branch_name=branch_name,
                rel_path=rel_path,
            )
            symbol_rows.extend(file_symbols)
            dep_rows.extend(file_deps)
            stats.symbols += len(file_symbols)
            stats.dependencies += len(file_deps)

            chunks = self._make_chunks(content, max_lines=60)
            for start_line, end_line, chunk_text in chunks:
                keywords = self._keywords(chunk_text)
                chunk_rows.append(
                    KnowledgeChunkEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        source_type="code",
                        source_path=rel_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_text=chunk_text,
                        keywords=",".join(keywords[:12]) if keywords else None,
                    )
                )
            stats.chunks += len(chunks)

        self.repo.add_project_files(file_rows)
        self.repo.add_code_symbols(symbol_rows)
        self.repo.add_dependency_edges(dep_rows)
        self.repo.add_knowledge_chunks(chunk_rows)
        return stats

    def _extract_symbols_and_dependencies(
        self,
        content: str,
        suffix: str,
        repo_name: str,
        branch_name: str,
        rel_path: str,
    ) -> tuple[list[CodeSymbolEntity], list[DependencyEdgeEntity]]:
        if suffix == ".py":
            return self._extract_python(content, repo_name, branch_name, rel_path)
        if suffix in {".ts", ".tsx", ".js"}:
            return self._extract_ts_js(content, repo_name, branch_name, rel_path)
        return [], []

    def _extract_python(
        self,
        content: str,
        repo_name: str,
        branch_name: str,
        rel_path: str,
    ) -> tuple[list[CodeSymbolEntity], list[DependencyEdgeEntity]]:
        symbols: list[CodeSymbolEntity] = []
        deps: list[DependencyEdgeEntity] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return symbols, deps

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    CodeSymbolEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        file_path=rel_path,
                        symbol_name=node.name,
                        symbol_type="class",
                        start_line=getattr(node, "lineno", 1),
                        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        signature=f"class {node.name}",
                        docstring=ast.get_docstring(node),
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arg_names = [a.arg for a in node.args.args]
                signature = f"{node.name}({', '.join(arg_names)})"
                symbols.append(
                    CodeSymbolEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        file_path=rel_path,
                        symbol_name=node.name,
                        symbol_type="function",
                        start_line=getattr(node, "lineno", 1),
                        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        signature=signature,
                        docstring=ast.get_docstring(node),
                    )
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    deps.append(
                        DependencyEdgeEntity(
                            repo_name=repo_name,
                            branch_name=branch_name,
                            source_file=rel_path,
                            target_module=alias.name,
                            edge_type="import",
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.append(
                        DependencyEdgeEntity(
                            repo_name=repo_name,
                            branch_name=branch_name,
                            source_file=rel_path,
                            target_module=node.module,
                            edge_type="from_import",
                        )
                    )

        return symbols, deps

    def _extract_ts_js(
        self,
        content: str,
        repo_name: str,
        branch_name: str,
        rel_path: str,
    ) -> tuple[list[CodeSymbolEntity], list[DependencyEdgeEntity]]:
        symbols: list[CodeSymbolEntity] = []
        deps: list[DependencyEdgeEntity] = []

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            class_match = CLASS_PATTERN.search(line)
            if class_match:
                name = class_match.group(1)
                symbols.append(
                    CodeSymbolEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        file_path=rel_path,
                        symbol_name=name,
                        symbol_type="class",
                        start_line=idx,
                        end_line=idx,
                        signature=f"class {name}",
                    )
                )

            fn_match = FUNCTION_PATTERN.search(line)
            if fn_match:
                name = fn_match.group(1)
                signature = f"{name}({fn_match.group(2).strip()})"
                symbols.append(
                    CodeSymbolEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        file_path=rel_path,
                        symbol_name=name,
                        symbol_type="function",
                        start_line=idx,
                        end_line=idx,
                        signature=signature,
                    )
                )

            for pattern in (IMPORT_PATTERN, REQUIRE_PATTERN):
                dep_match = pattern.search(line)
                if dep_match:
                    deps.append(
                        DependencyEdgeEntity(
                            repo_name=repo_name,
                            branch_name=branch_name,
                            source_file=rel_path,
                            target_module=dep_match.group(1),
                            edge_type="import",
                        )
                    )

        return symbols, deps

    def _make_chunks(self, content: str, max_lines: int = 60) -> list[tuple[int, int, str]]:
        lines = content.splitlines()
        chunks: list[tuple[int, int, str]] = []
        for idx in range(0, len(lines), max_lines):
            part = lines[idx : idx + max_lines]
            if not part:
                continue
            chunks.append((idx + 1, idx + len(part), "\n".join(part)))
        return chunks

    def _keywords(self, text: str) -> list[str]:
        words = TOKEN_PATTERN.findall(text)
        dedup: list[str] = []
        seen: set[str] = set()
        for word in words:
            norm = word.lower()
            if norm in seen:
                continue
            seen.add(norm)
            dedup.append(norm)
        return dedup


class ContextRetriever:
    def __init__(self, repo: ContextRepository):
        self.repo = repo

    def retrieve(
        self,
        query: str,
        session_id: str,
        repo_name: str,
        branch_name: str,
    ) -> str:
        keywords = self._keywords(query)
        memories = self.repo.list_session_memories(session_id=session_id, limit=120)
        symbols = self.repo.search_symbols(repo_name=repo_name, branch_name=branch_name, keywords=keywords, limit=20)
        deps = self.repo.search_dependencies(repo_name=repo_name, branch_name=branch_name, keywords=keywords, limit=20)
        chunks = self.repo.search_knowledge_chunks(repo_name=repo_name, branch_name=branch_name, keywords=keywords, limit=30)

        dep_files = {d.source_file for d in deps}

        top_memories = self._rank_memories(memories, keywords, limit=8)
        top_symbols = self._rank_symbols(symbols, keywords, limit=10)
        top_deps = self._rank_dependencies(deps, keywords, limit=10)
        top_chunks = self._rank_chunks(chunks, keywords, dep_files, limit=8)

        sections: list[str] = []
        if top_memories:
            section = ["[Memory]"]
            for m in top_memories:
                section.append(f"- {m.role}: {m.content[:200]}")
            sections.append("\n".join(section))

        if top_symbols:
            section = ["[Symbols]"]
            for s in top_symbols:
                section.append(f"- {s.file_path}:{s.start_line} {s.symbol_type} {s.symbol_name} {s.signature or ''}".strip())
            sections.append("\n".join(section))

        if top_deps:
            section = ["[Dependencies]"]
            for d in top_deps:
                section.append(f"- {d.source_file} -> {d.target_module} ({d.edge_type})")
            sections.append("\n".join(section))

        if top_chunks:
            section = ["[Knowledge]"]
            for c in top_chunks:
                preview = c.chunk_text.strip().replace("\n", " ")[:220]
                section.append(f"- {c.source_path}:{c.start_line}-{c.end_line} {preview}")
            sections.append("\n".join(section))

        if not sections:
            return "no indexed context available"

        return self._trim_to_budget("\n\n".join(sections), max_chars=5000)

    def _keywords(self, text: str) -> list[str]:
        terms = TOKEN_PATTERN.findall(text.lower())
        seen: set[str] = set()
        out: list[str] = []
        for t in terms:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:8]

    def _token_overlap(self, text: str, keywords: list[str]) -> int:
        if not keywords:
            return 0
        lowered = text.lower()
        return sum(1 for k in keywords if k in lowered)

    def _rank_memories(self, memories: list, keywords: list[str], limit: int) -> list:
        ranked: list[tuple[float, object]] = []
        total = len(memories)
        for idx, m in enumerate(memories):
            overlap = self._token_overlap(m.content, keywords)
            recency_score = (total - idx) / max(1, total)
            summary_bonus = 0.6 if m.role == "summary" else 0.0
            score = overlap * 1.7 + recency_score + (m.importance_score * 0.4) + summary_bonus
            ranked.append((score, m))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in ranked[:limit]]

    def _rank_symbols(self, symbols: list, keywords: list[str], limit: int) -> list:
        ranked: list[tuple[int, object]] = []
        for s in symbols:
            text = f"{s.symbol_name} {s.signature or ''}"
            ranked.append((self._token_overlap(text, keywords), s))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in ranked[:limit]]

    def _rank_dependencies(self, deps: list, keywords: list[str], limit: int) -> list:
        ranked: list[tuple[int, object]] = []
        for d in deps:
            text = f"{d.source_file} {d.target_module}"
            ranked.append((self._token_overlap(text, keywords), d))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in ranked[:limit]]

    def _rank_chunks(self, chunks: list, keywords: list[str], dep_files: set[str], limit: int) -> list:
        ranked: list[tuple[float, object]] = []
        for c in chunks:
            overlap = self._token_overlap(c.chunk_text, keywords)
            dep_boost = 1.2 if c.source_path in dep_files else 0.0
            keyword_boost = 0.4 if c.keywords else 0.0
            score = overlap * 1.5 + dep_boost + keyword_boost
            ranked.append((score, c))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in ranked[:limit]]

    def _trim_to_budget(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 50] + "\n\n[Truncated to context budget]"
