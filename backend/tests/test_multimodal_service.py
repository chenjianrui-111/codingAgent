from pathlib import Path

from app.services.multimodal_service import MultimodalPreprocessor


def test_multimodal_preprocess_uses_inline_text():
    svc = MultimodalPreprocessor()
    result = svc.preprocess(
        query="implement login api",
        attachments=[{"kind": "text", "text": "需求补充：加上速率限制"}],
    )
    assert result.attachment_count == 1
    assert result.extracted_count == 1
    assert "ATTACHMENT_CONTEXT" in result.enriched_query
    assert "速率限制" in result.enriched_query


def test_multimodal_preprocess_reads_text_file(tmp_path: Path):
    note = tmp_path / "note.txt"
    note.write_text("UI 规范：按钮改为蓝色", encoding="utf-8")

    svc = MultimodalPreprocessor()
    result = svc.preprocess(
        query="update frontend",
        attachments=[{"kind": "document", "path": str(note)}],
    )

    assert result.processed_count == 1
    assert result.failed_count == 0
    assert "按钮改为蓝色" in result.enriched_query


def test_multimodal_preprocess_fails_without_readable_source():
    svc = MultimodalPreprocessor()
    result = svc.preprocess(
        query="fix bug",
        attachments=[{"kind": "audio", "path": "/tmp/not-found-audio.mp3"}],
    )
    assert result.attachment_count == 1
    assert result.failed_count == 1
    assert result.enriched_query == "fix bug"
