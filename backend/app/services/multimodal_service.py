from __future__ import annotations

import base64
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import which


TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".ts", ".tsx", ".js", ".java"}


@dataclass
class PreprocessedAttachment:
    kind: str
    source: str
    extracted_text: str
    status: str
    note: str


@dataclass
class MultimodalPreprocessResult:
    enriched_query: str
    attachment_count: int
    processed_count: int
    extracted_count: int
    failed_count: int
    notes: list[str]
    extracted_items: list[PreprocessedAttachment]


class MultimodalPreprocessor:
    def preprocess(self, query: str, attachments: list[dict] | None = None) -> MultimodalPreprocessResult:
        items = attachments or []
        extracted_items: list[PreprocessedAttachment] = []
        notes: list[str] = []

        for idx, item in enumerate(items, start=1):
            extracted = self._extract_attachment(item, idx)
            extracted_items.append(extracted)
            if extracted.note:
                notes.append(f"attachment#{idx}: {extracted.note}")

        successful = [x for x in extracted_items if x.status == "ok"]
        extracted_blocks = [x for x in successful if x.extracted_text.strip()]
        if extracted_blocks:
            context_lines = ["[ATTACHMENT_CONTEXT]"]
            for idx, block in enumerate(extracted_blocks, start=1):
                context_lines.append(f"{idx}. kind={block.kind} source={block.source}")
                context_lines.append(block.extracted_text.strip()[:1600])
            enriched_query = f"{query}\n\n" + "\n".join(context_lines)
        else:
            enriched_query = query

        return MultimodalPreprocessResult(
            enriched_query=enriched_query,
            attachment_count=len(items),
            processed_count=len(successful),
            extracted_count=len(extracted_blocks),
            failed_count=len(items) - len(successful),
            notes=notes[:12],
            extracted_items=extracted_items,
        )

    def _extract_attachment(self, item: dict, idx: int) -> PreprocessedAttachment:
        kind = str(item.get("kind") or "text").lower()
        inline_text = (item.get("text") or "").strip()
        name = item.get("file_name") or item.get("path") or f"attachment_{idx}"
        source = str(name)

        if inline_text:
            return PreprocessedAttachment(
                kind=kind,
                source=source,
                extracted_text=inline_text,
                status="ok",
                note="used inline text",
            )

        path_str = item.get("path")
        path = self._resolve_path(path_str) if path_str else None
        if path and path.exists():
            result = self._extract_from_path(kind, path)
            if result is not None:
                return result

        content_b64 = item.get("content_base64")
        if isinstance(content_b64, str) and content_b64.strip():
            result = self._extract_from_base64(kind, content_b64.strip(), item.get("mime_type"), source)
            if result is not None:
                return result

        return PreprocessedAttachment(
            kind=kind,
            source=source,
            extracted_text="",
            status="failed",
            note="no readable text source found",
        )

    def _extract_from_path(self, kind: str, path: Path) -> PreprocessedAttachment | None:
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
                return PreprocessedAttachment(
                    kind=kind,
                    source=str(path),
                    extracted_text=text[:3000],
                    status="ok",
                    note="read from text file",
                )
            except Exception:
                return None

        if kind == "image":
            text = self._run_tesseract(path)
            if text:
                return PreprocessedAttachment(
                    kind=kind,
                    source=str(path),
                    extracted_text=text[:3000],
                    status="ok",
                    note="ocr by tesseract",
                )
            return PreprocessedAttachment(
                kind=kind,
                source=str(path),
                extracted_text="",
                status="failed",
                note="ocr tool unavailable or no text extracted",
            )

        if kind == "audio":
            text = self._run_whisper(path)
            if text:
                return PreprocessedAttachment(
                    kind=kind,
                    source=str(path),
                    extracted_text=text[:3000],
                    status="ok",
                    note="asr by whisper cli",
                )
            return PreprocessedAttachment(
                kind=kind,
                source=str(path),
                extracted_text="",
                status="failed",
                note="asr tool unavailable or no transcript extracted",
            )

        return None

    def _extract_from_base64(
        self,
        kind: str,
        content_b64: str,
        mime_type: str | None,
        source: str,
    ) -> PreprocessedAttachment | None:
        try:
            raw = base64.b64decode(content_b64, validate=True)
        except Exception:
            return PreprocessedAttachment(
                kind=kind,
                source=source,
                extracted_text="",
                status="failed",
                note="invalid base64",
            )

        if kind == "text":
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return PreprocessedAttachment(
                    kind=kind,
                    source=source,
                    extracted_text="",
                    status="failed",
                    note="text base64 is not utf-8",
                )
            return PreprocessedAttachment(
                kind=kind,
                source=source,
                extracted_text=text[:3000],
                status="ok",
                note="decoded from base64 text",
            )

        suffix = self._suffix_from_mime(kind, mime_type)
        with tempfile.NamedTemporaryFile(prefix="mm_", suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            result = self._extract_from_path(kind, tmp_path)
            if result:
                return result
            return PreprocessedAttachment(
                kind=kind,
                source=source,
                extracted_text="",
                status="failed",
                note="unable to process binary base64 attachment",
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _run_tesseract(self, path: Path) -> str:
        if which("tesseract") is None:
            return ""
        try:
            proc = subprocess.run(
                ["tesseract", str(path), "stdout"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()

    def _run_whisper(self, path: Path) -> str:
        if which("whisper") is None:
            return ""
        with tempfile.TemporaryDirectory(prefix="mm_asr_") as out_dir:
            try:
                proc = subprocess.run(
                    [
                        "whisper",
                        str(path),
                        "--model",
                        "tiny",
                        "--task",
                        "transcribe",
                        "--output_format",
                        "txt",
                        "--output_dir",
                        out_dir,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except Exception:
                return ""
            if proc.returncode != 0:
                return ""
            candidates = sorted(Path(out_dir).glob("*.txt"))
            if not candidates:
                return ""
            try:
                return candidates[0].read_text(encoding="utf-8").strip()
            except Exception:
                return ""

    def _suffix_from_mime(self, kind: str, mime_type: str | None) -> str:
        mime = (mime_type or "").lower()
        if kind == "image":
            if "png" in mime:
                return ".png"
            if "jpeg" in mime or "jpg" in mime:
                return ".jpg"
            return ".img"
        if kind == "audio":
            if "wav" in mime:
                return ".wav"
            if "mpeg" in mime or "mp3" in mime:
                return ".mp3"
            return ".audio"
        if kind == "document":
            if "pdf" in mime:
                return ".pdf"
            return ".doc"
        return ".bin"

    def _resolve_path(self, path_str: str | None) -> Path | None:
        if not path_str:
            return None
        raw = Path(path_str)
        if raw.is_absolute():
            return raw
        cwd_path = Path.cwd() / raw
        if cwd_path.exists():
            return cwd_path
        return raw
