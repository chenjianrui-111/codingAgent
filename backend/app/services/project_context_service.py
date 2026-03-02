from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.models import ProjectGraphEdgeEntity, ProjectGraphNodeEntity, ProjectVectorEntity
from app.repositories.context_repo import ContextRepository
from app.services.context_service import ContextIndexer


CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".java"}
DOC_SUFFIXES = {".md", ".rst", ".adoc"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".xml", ".properties", ".env"}
CORE_CONFIG_NAMES = {
    "pom.xml",
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    "README.md",
    "README.MD",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}")
IMPORT_FROM_PATTERN = re.compile(r"import\s+.*?from\s+[\"']([^\"']+)[\"']")
IMPORT_REQUIRE_PATTERN = re.compile(r"require\([\"']([^\"']+)[\"']\)")
TS_FUNCTION_PATTERN = re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)")
TS_CLASS_PATTERN = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+([A-Za-z_][A-Za-z0-9_]*))?")
TS_CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@dataclass
class SymbolInfo:
    node_key: str
    name: str
    symbol_type: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str | None


@dataclass
class ParsedFile:
    rel_path: str
    suffix: str
    kind: str
    content: str
    symbol_infos: list[SymbolInfo]
    imports: list[str]
    calls_by_symbol: dict[str, list[str]]
    inheritance: list[tuple[str, str]]


@dataclass
class ProjectInitStats:
    scoped_workspace: str
    indexed_files: int
    graph_nodes: int
    graph_edges: int
    vectors: int


@dataclass
class ProjectContextResult:
    context: str
    selected_files: list[str]


class ProjectContextManager:
    def __init__(self, repo: ContextRepository):
        self.repo = repo

    def initialize_project(
        self,
        workspace: str,
        repo_name: str,
        branch_name: str,
        module_path: str | None = None,
    ) -> ProjectInitStats:
        root = Path(workspace).resolve()
        scoped_root = (root / module_path).resolve() if module_path else root
        if not scoped_root.exists() or not scoped_root.is_dir():
            raise FileNotFoundError(f"workspace not found: {scoped_root}")

        # Rebuild base context tables first (files/symbols/dependencies/chunks).
        base_stats = ContextIndexer(self.repo).index_workspace(str(scoped_root), repo_name, branch_name)

        parsed_files = self._parse_files(root, scoped_root)

        node_map: dict[str, ProjectGraphNodeEntity] = {}
        edge_map: dict[tuple[str, str, str], ProjectGraphEdgeEntity] = {}
        vector_map: dict[str, ProjectVectorEntity] = {}
        symbol_name_to_keys: dict[str, list[str]] = {}
        file_keys: set[str] = set()

        # First pass: file/symbol nodes + vectors.
        for parsed in parsed_files:
            file_key = f"file::{parsed.rel_path}"
            file_keys.add(file_key)
            node_map[file_key] = ProjectGraphNodeEntity(
                repo_name=repo_name,
                branch_name=branch_name,
                node_key=file_key,
                node_type=parsed.kind,
                name=Path(parsed.rel_path).name,
                file_path=parsed.rel_path,
                metadata_json=json.dumps({"suffix": parsed.suffix}),
            )
            vector_map[file_key] = self._build_vector_entity(
                repo_name=repo_name,
                branch_name=branch_name,
                entity_key=file_key,
                entity_type=parsed.kind,
                file_path=parsed.rel_path,
                text_content=self._build_file_text(parsed),
            )

            for symbol in parsed.symbol_infos:
                node_map[symbol.node_key] = ProjectGraphNodeEntity(
                    repo_name=repo_name,
                    branch_name=branch_name,
                    node_key=symbol.node_key,
                    node_type=symbol.symbol_type,
                    name=symbol.name,
                    file_path=symbol.file_path,
                    metadata_json=json.dumps(
                        {
                            "start_line": symbol.start_line,
                            "end_line": symbol.end_line,
                            "signature": symbol.signature,
                        }
                    ),
                )
                symbol_name_to_keys.setdefault(symbol.name, []).append(symbol.node_key)

                edge_key = (file_key, symbol.node_key, "contains")
                edge_map[edge_key] = ProjectGraphEdgeEntity(
                    repo_name=repo_name,
                    branch_name=branch_name,
                    source_key=file_key,
                    target_key=symbol.node_key,
                    edge_type="contains",
                    weight=1,
                )
                vector_map[symbol.node_key] = self._build_vector_entity(
                    repo_name=repo_name,
                    branch_name=branch_name,
                    entity_key=symbol.node_key,
                    entity_type=symbol.symbol_type,
                    file_path=symbol.file_path,
                    text_content=self._build_symbol_text(symbol),
                )

        # Second pass: dependencies, inheritance, calls.
        for parsed in parsed_files:
            file_key = f"file::{parsed.rel_path}"

            for imported in parsed.imports:
                target_file_key = self._resolve_import_to_file_key(imported, parsed.rel_path, file_keys)
                if target_file_key:
                    edge_key = (file_key, target_file_key, "depends_on")
                    edge_map[edge_key] = ProjectGraphEdgeEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        source_key=file_key,
                        target_key=target_file_key,
                        edge_type="depends_on",
                        weight=1,
                    )
                else:
                    module_key = f"module::{imported}"
                    if module_key not in node_map:
                        node_map[module_key] = ProjectGraphNodeEntity(
                            repo_name=repo_name,
                            branch_name=branch_name,
                            node_key=module_key,
                            node_type="module",
                            name=imported,
                            file_path=None,
                        )
                    edge_key = (file_key, module_key, "depends_on")
                    edge_map[edge_key] = ProjectGraphEdgeEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        source_key=file_key,
                        target_key=module_key,
                        edge_type="depends_on",
                        weight=1,
                    )

            for class_key, base_name in parsed.inheritance:
                for target_key in symbol_name_to_keys.get(base_name, []):
                    edge_key = (class_key, target_key, "extends")
                    edge_map[edge_key] = ProjectGraphEdgeEntity(
                        repo_name=repo_name,
                        branch_name=branch_name,
                        source_key=class_key,
                        target_key=target_key,
                        edge_type="extends",
                        weight=1,
                    )

            for source_symbol_key, calls in parsed.calls_by_symbol.items():
                source_file = self._file_from_symbol_key(source_symbol_key)
                for callee in calls:
                    for target_symbol_key in symbol_name_to_keys.get(callee, []):
                        edge_key = (source_symbol_key, target_symbol_key, "calls")
                        edge_map[edge_key] = ProjectGraphEdgeEntity(
                            repo_name=repo_name,
                            branch_name=branch_name,
                            source_key=source_symbol_key,
                            target_key=target_symbol_key,
                            edge_type="calls",
                            weight=1,
                        )
                        target_file = self._file_from_symbol_key(target_symbol_key)
                        if source_file and target_file and source_file != target_file:
                            file_edge_key = (f"file::{source_file}", f"file::{target_file}", "calls_file")
                            edge_map[file_edge_key] = ProjectGraphEdgeEntity(
                                repo_name=repo_name,
                                branch_name=branch_name,
                                source_key=f"file::{source_file}",
                                target_key=f"file::{target_file}",
                                edge_type="calls_file",
                                weight=1,
                            )

        self.repo.add_graph_nodes(list(node_map.values()))
        self.repo.add_graph_edges(list(edge_map.values()))
        self.repo.add_project_vectors(list(vector_map.values()))

        return ProjectInitStats(
            scoped_workspace=str(scoped_root),
            indexed_files=base_stats.files,
            graph_nodes=len(node_map),
            graph_edges=len(edge_map),
            vectors=len(vector_map),
        )

    def retrieve_project_context(
        self,
        query: str,
        repo_name: str,
        branch_name: str,
        current_file: str | None = None,
        max_items: int | None = None,
    ) -> ProjectContextResult:
        keywords = self._keywords(query)
        query_embedding = self._embedding(query)
        candidates = self.repo.search_project_vectors(repo_name, branch_name, keywords=keywords, limit=300)
        core_vectors = self.repo.list_core_config_vectors(repo_name, branch_name, limit=25)

        vec_by_key: dict[str, ProjectVectorEntity] = {}
        for vec in candidates + core_vectors:
            vec_by_key[vec.entity_key] = vec
        if not vec_by_key:
            return ProjectContextResult(context="no indexed context available", selected_files=[])

        direct_files, indirect_files = self._dependency_layers(repo_name, branch_name, current_file)

        scored: list[tuple[float, ProjectVectorEntity]] = []
        for vec in vec_by_key.values():
            similarity = self._cosine(query_embedding, self._parse_embedding(vec.embedding_json))
            overlap = self._overlap_score(vec.text_content, keywords)
            priority = self._file_priority(vec.file_path, current_file, direct_files, indirect_files)
            score = similarity + overlap * 0.15 + priority
            scored.append((score, vec))

        scored.sort(key=lambda item: item[0], reverse=True)
        limit = max_items or settings.project_context_max_items
        picked = scored[: max(1, limit)]
        if not picked:
            return ProjectContextResult(context="no indexed context available", selected_files=[])

        lines: list[str] = ["[ProjectContext]"]
        selected_files: list[str] = []
        for idx, (score, vec) in enumerate(picked, start=1):
            file_label = vec.file_path or "<external>"
            if vec.file_path:
                selected_files.append(vec.file_path)
            preview = vec.text_content.replace("\n", " ")[:240]
            lines.append(f"{idx}. ({score:.3f}) [{vec.entity_type}] {file_label} :: {preview}")

        dedup_files = sorted(set(selected_files))
        if current_file:
            lines.append(f"Current file: {current_file}")
        if direct_files:
            lines.append("Direct deps: " + ", ".join(sorted(direct_files)[:8]))
        if indirect_files:
            lines.append("Indirect deps: " + ", ".join(sorted(indirect_files)[:8]))

        context_text = "\n".join(lines)
        budget = settings.memory_context_char_budget
        if len(context_text) > budget:
            context_text = context_text[: budget - 40] + "\n[Truncated]"

        return ProjectContextResult(context=context_text, selected_files=dedup_files)

    def caller_files_of_function(self, repo_name: str, branch_name: str, function_name: str) -> list[str]:
        symbol_nodes = self.repo.list_symbol_nodes_by_name(repo_name, branch_name, symbol_name=function_name, limit=200)
        if not symbol_nodes:
            return []
        target_keys = [n.node_key for n in symbol_nodes]
        edges = self.repo.list_edges_to_targets(repo_name, branch_name, target_keys=target_keys, edge_type="calls", limit=800)
        source_keys = [e.source_key for e in edges]
        source_nodes = self.repo.list_nodes_by_keys(repo_name, branch_name, source_keys)
        files = sorted({n.file_path for n in source_nodes if n.file_path})
        return files

    def _parse_files(self, root: Path, scoped_root: Path) -> list[ParsedFile]:
        parsed: list[ParsedFile] = []
        for path in scoped_root.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            kind = self._file_kind(path)
            if kind is None:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            rel_path = str(path.relative_to(root))
            symbol_infos: list[SymbolInfo] = []
            imports: list[str] = []
            calls_by_symbol: dict[str, list[str]] = {}
            inheritance: list[tuple[str, str]] = []

            if suffix == ".py":
                symbol_infos, imports, calls_by_symbol, inheritance = self._parse_python(rel_path, content)
            elif suffix in {".ts", ".tsx", ".js"}:
                symbol_infos, imports, calls_by_symbol, inheritance = self._parse_ts_js(rel_path, content)

            parsed.append(
                ParsedFile(
                    rel_path=rel_path,
                    suffix=suffix,
                    kind=kind,
                    content=content,
                    symbol_infos=symbol_infos,
                    imports=imports,
                    calls_by_symbol=calls_by_symbol,
                    inheritance=inheritance,
                )
            )
        return parsed

    def _file_kind(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix in CODE_SUFFIXES:
            return "file"
        if suffix in DOC_SUFFIXES or path.name.lower().startswith("readme"):
            return "doc"
        if suffix in CONFIG_SUFFIXES or path.name in CORE_CONFIG_NAMES:
            return "config"
        return None

    def _parse_python(
        self,
        rel_path: str,
        content: str,
    ) -> tuple[list[SymbolInfo], list[str], dict[str, list[str]], list[tuple[str, str]]]:
        symbols: list[SymbolInfo] = []
        imports: list[str] = []
        calls_by_symbol: dict[str, list[str]] = {}
        inheritance: list[tuple[str, str]] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return symbols, imports, calls_by_symbol, inheritance

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_key = f"symbol::{rel_path}::{node.name}"
                symbols.append(
                    SymbolInfo(
                        node_key=class_key,
                        name=node.name,
                        symbol_type="class",
                        file_path=rel_path,
                        start_line=getattr(node, "lineno", 1),
                        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        signature=f"class {node.name}",
                        docstring=ast.get_docstring(node),
                    )
                )
                for base in node.bases:
                    base_name = self._ast_name(base)
                    if base_name:
                        inheritance.append((class_key, base_name))
                calls_by_symbol[class_key] = self._extract_call_names(node)

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_name = f"{node.name}.{item.name}"
                        method_key = f"symbol::{rel_path}::{method_name}"
                        arg_names = [a.arg for a in item.args.args]
                        symbols.append(
                            SymbolInfo(
                                node_key=method_key,
                                name=item.name,
                                symbol_type="function",
                                file_path=rel_path,
                                start_line=getattr(item, "lineno", 1),
                                end_line=getattr(item, "end_lineno", getattr(item, "lineno", 1)),
                                signature=f"{item.name}({', '.join(arg_names)})",
                                docstring=ast.get_docstring(item),
                            )
                        )
                        calls_by_symbol[method_key] = self._extract_call_names(item)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_key = f"symbol::{rel_path}::{node.name}"
                arg_names = [a.arg for a in node.args.args]
                symbols.append(
                    SymbolInfo(
                        node_key=fn_key,
                        name=node.name,
                        symbol_type="function",
                        file_path=rel_path,
                        start_line=getattr(node, "lineno", 1),
                        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        signature=f"{node.name}({', '.join(arg_names)})",
                        docstring=ast.get_docstring(node),
                    )
                )
                calls_by_symbol[fn_key] = self._extract_call_names(node)

        return symbols, sorted(set(imports)), calls_by_symbol, inheritance

    def _parse_ts_js(
        self,
        rel_path: str,
        content: str,
    ) -> tuple[list[SymbolInfo], list[str], dict[str, list[str]], list[tuple[str, str]]]:
        symbols: list[SymbolInfo] = []
        imports: list[str] = []
        calls_by_symbol: dict[str, list[str]] = {}
        inheritance: list[tuple[str, str]] = []

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            for pattern in (IMPORT_FROM_PATTERN, IMPORT_REQUIRE_PATTERN):
                m = pattern.search(line)
                if m:
                    imports.append(m.group(1))

            class_match = TS_CLASS_PATTERN.search(line)
            if class_match:
                class_name = class_match.group(1)
                base_name = class_match.group(2)
                class_key = f"symbol::{rel_path}::{class_name}"
                symbols.append(
                    SymbolInfo(
                        node_key=class_key,
                        name=class_name,
                        symbol_type="class",
                        file_path=rel_path,
                        start_line=idx,
                        end_line=idx,
                        signature=f"class {class_name}",
                        docstring=None,
                    )
                )
                calls_by_symbol[class_key] = []
                if base_name:
                    inheritance.append((class_key, base_name))

            fn_match = TS_FUNCTION_PATTERN.search(line)
            if fn_match:
                fn_name = fn_match.group(1)
                fn_key = f"symbol::{rel_path}::{fn_name}"
                symbols.append(
                    SymbolInfo(
                        node_key=fn_key,
                        name=fn_name,
                        symbol_type="function",
                        file_path=rel_path,
                        start_line=idx,
                        end_line=idx,
                        signature=f"{fn_name}({fn_match.group(2).strip()})",
                        docstring=None,
                    )
                )
                calls_by_symbol[fn_key] = [c for c in TS_CALL_PATTERN.findall(line) if c not in {fn_name, "if", "for", "while", "switch"}]

        return symbols, sorted(set(imports)), calls_by_symbol, inheritance

    def _extract_call_names(self, node: ast.AST) -> list[str]:
        calls: list[str] = []
        for item in ast.walk(node):
            if isinstance(item, ast.Call):
                name = self._ast_name(item.func)
                if name:
                    calls.append(name)
        return sorted(set(calls))

    def _ast_name(self, node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _resolve_import_to_file_key(self, imported: str, source_rel_path: str, file_keys: set[str]) -> str | None:
        if imported.startswith("."):
            base_dir = str(Path(source_rel_path).parent)
            stripped = imported.lstrip(".")
            raw = (Path(base_dir) / stripped).as_posix()
            rel_candidates = [
                f"file::{raw}.py",
                f"file::{raw}/__init__.py",
                f"file::{raw}.ts",
                f"file::{raw}.tsx",
                f"file::{raw}.js",
                f"file::{raw}/index.ts",
                f"file::{raw}/index.tsx",
                f"file::{raw}/index.js",
            ]
            for candidate in rel_candidates:
                if candidate in file_keys:
                    return candidate

        normalized = imported.replace(".", "/")
        candidates = [
            f"file::{normalized}.py",
            f"file::{normalized}/__init__.py",
            f"file::{normalized}.ts",
            f"file::{normalized}.tsx",
            f"file::{normalized}.js",
        ]
        for candidate in candidates:
            if candidate in file_keys:
                return candidate
        return None

    def _file_from_symbol_key(self, symbol_key: str) -> str | None:
        if not symbol_key.startswith("symbol::"):
            return None
        body = symbol_key[len("symbol::") :]
        parts = body.split("::")
        if len(parts) < 2:
            return None
        return parts[0]

    def _build_file_text(self, parsed: ParsedFile) -> str:
        import_text = ", ".join(parsed.imports[:12]) if parsed.imports else "none"
        symbol_names = ", ".join([s.name for s in parsed.symbol_infos[:16]]) if parsed.symbol_infos else "none"
        content_preview = parsed.content[:1800]
        return (
            f"File path: {parsed.rel_path}\n"
            f"Kind: {parsed.kind}\n"
            f"Imports: {import_text}\n"
            f"Symbols: {symbol_names}\n"
            f"Content:\n{content_preview}"
        )

    def _build_symbol_text(self, symbol: SymbolInfo) -> str:
        doc = symbol.docstring or ""
        return (
            f"Symbol: {symbol.name}\n"
            f"Type: {symbol.symbol_type}\n"
            f"File: {symbol.file_path}:{symbol.start_line}-{symbol.end_line}\n"
            f"Signature: {symbol.signature}\n"
            f"Doc: {doc}"
        )

    def _build_vector_entity(
        self,
        repo_name: str,
        branch_name: str,
        entity_key: str,
        entity_type: str,
        file_path: str | None,
        text_content: str,
    ) -> ProjectVectorEntity:
        keywords = self._keywords(text_content)
        embedding = self._embedding(text_content)
        return ProjectVectorEntity(
            repo_name=repo_name,
            branch_name=branch_name,
            entity_key=entity_key,
            entity_type=entity_type,
            file_path=file_path,
            text_content=text_content[:5000],
            embedding_json=json.dumps(embedding),
            keywords=",".join(keywords[:20]) if keywords else None,
        )

    def _keywords(self, text: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for token in TOKEN_PATTERN.findall(text.lower()):
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

    def _embedding(self, text: str) -> list[float]:
        dim = max(16, settings.project_vector_dim)
        vec = [0.0] * dim
        for token in self._keywords(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], byteorder="big") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [round(v / norm, 6) for v in vec]

    def _parse_embedding(self, embedding_json: str) -> list[float]:
        try:
            values = json.loads(embedding_json)
            if isinstance(values, list):
                return [float(x) for x in values]
        except Exception:
            pass
        return [0.0] * max(16, settings.project_vector_dim)

    def _cosine(self, a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        return sum(a[i] * b[i] for i in range(n))

    def _overlap_score(self, text: str, keywords: list[str]) -> float:
        lowered = text.lower()
        matched = sum(1 for k in keywords if k in lowered)
        return matched / max(1, len(keywords))

    def _file_priority(
        self,
        file_path: str | None,
        current_file: str | None,
        direct_files: set[str],
        indirect_files: set[str],
    ) -> float:
        if not file_path:
            return 0.0
        if current_file and file_path == current_file:
            return 2.5
        if file_path in direct_files:
            return 1.4
        if file_path in indirect_files:
            return 0.8
        if Path(file_path).name in CORE_CONFIG_NAMES:
            return 0.5
        return 0.0

    def _dependency_layers(self, repo_name: str, branch_name: str, current_file: str | None) -> tuple[set[str], set[str]]:
        if not current_file:
            return set(), set()

        current_key = f"file::{current_file}"
        edges = self.repo.list_graph_neighbors(repo_name, branch_name, node_key=current_key, limit=300)
        direct: set[str] = set()
        for edge in edges:
            neighbor = edge.target_key if edge.source_key == current_key else edge.source_key
            if neighbor.startswith("file::"):
                direct.add(neighbor[len("file::") :])

        direct_keys = [f"file::{p}" for p in direct]
        second_edges = self.repo.list_edges_from_sources(
            repo_name,
            branch_name,
            source_keys=direct_keys,
            edge_types=["depends_on", "calls_file"],
            limit=800,
        )
        indirect: set[str] = set()
        for edge in second_edges:
            if edge.target_key.startswith("file::"):
                path = edge.target_key[len("file::") :]
                if path != current_file and path not in direct:
                    indirect.add(path)

        if current_file in direct:
            direct.remove(current_file)
        return direct, indirect
