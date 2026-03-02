from types import SimpleNamespace

from app.services.project_context_service import ProjectContextManager


class FakeRepo:
    def __init__(self):
        self.vectors = []
        self.core_vectors = []
        self.neighbor_edges = []
        self.second_edges = []

    def search_project_vectors(self, repo_name, branch_name, keywords, limit=200):
        return self.vectors

    def list_core_config_vectors(self, repo_name, branch_name, limit=20):
        return self.core_vectors

    def list_graph_neighbors(self, repo_name, branch_name, node_key, limit=200):
        return self.neighbor_edges

    def list_edges_from_sources(self, repo_name, branch_name, source_keys, edge_types=None, limit=500):
        return self.second_edges

    def list_symbol_nodes_by_name(self, repo_name, branch_name, symbol_name, limit=100):
        return [SimpleNamespace(node_key="symbol::src/pay.py::run")]

    def list_edges_to_targets(self, repo_name, branch_name, target_keys, edge_type, limit=500):
        return [SimpleNamespace(source_key="symbol::src/caller.py::invoke")]

    def list_nodes_by_keys(self, repo_name, branch_name, node_keys):
        return [SimpleNamespace(file_path="src/caller.py")]


def test_project_context_prioritizes_current_file_and_deps():
    repo = FakeRepo()
    repo.vectors = [
        SimpleNamespace(
            entity_key="file::src/main.py",
            entity_type="file",
            file_path="src/main.py",
            text_content="payment retry main logic",
            embedding_json="[1.0,0.0,0.0,0.0]",
            keywords="payment,retry,main",
        ),
        SimpleNamespace(
            entity_key="file::src/helper.py",
            entity_type="file",
            file_path="src/helper.py",
            text_content="helper for retry backoff",
            embedding_json="[0.8,0.0,0.0,0.0]",
            keywords="helper,retry",
        ),
    ]
    repo.neighbor_edges = [
        SimpleNamespace(source_key="file::src/main.py", target_key="file::src/helper.py"),
    ]

    manager = ProjectContextManager(repo)
    result = manager.retrieve_project_context(
        query="optimize payment retry",
        repo_name="codingAgent",
        branch_name="main",
        current_file="src/main.py",
        max_items=2,
    )

    assert "src/main.py" in result.context
    assert result.selected_files
    assert result.selected_files[0] in {"src/helper.py", "src/main.py"}


def test_project_caller_files_lookup():
    manager = ProjectContextManager(FakeRepo())
    files = manager.caller_files_of_function("codingAgent", "main", "run")
    assert files == ["src/caller.py"]
