from app.services.rag_service import RAGService


def test_rag_service_returns_default_for_missing_workspace(tmp_path):
    service = RAGService(workspace=str(tmp_path / "missing"))
    result = service.retrieve_context("test")
    assert "workspace does not exist" in result
