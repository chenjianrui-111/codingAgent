"""Data ingestion, schema discovery, and dataset management service.

Handles CSV / Excel / JSON / Parquet file uploads, auto-detects schema
and generates descriptive statistics for downstream Data Agent analysis.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum file size: 200 MB
MAX_FILE_SIZE = 200 * 1024 * 1024
SAMPLE_ROWS = 5
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet", ".tsv"}


@dataclass
class ColumnMeta:
    name: str
    dtype: str
    nullable: bool = True
    unique_count: int = 0
    null_count: int = 0
    min_value: str | None = None
    max_value: str | None = None
    mean_value: str | None = None
    sample_values: list[str] = field(default_factory=list)


@dataclass
class DatasetProfile:
    """Result of profiling an uploaded dataset."""

    dataset_id: str
    name: str
    file_path: str
    file_type: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: list[ColumnMeta]
    summary: dict[str, Any]
    sample_rows: list[dict[str, Any]]


class DataService:
    """Manages dataset upload, profiling, and storage."""

    def __init__(self, storage_root: str | None = None):
        self.storage_root = Path(storage_root or settings.sandbox_workspace_root) / "datasets"
        self.storage_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Upload & Profile
    # ------------------------------------------------------------------
    def ingest_file(
        self,
        file_data: BinaryIO,
        filename: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> DatasetProfile:
        """Save an uploaded file and profile its contents.

        Returns a ``DatasetProfile`` ready to be persisted to the DB.
        """
        import pandas as pd

        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

        dataset_id = str(uuid.uuid4())
        dest_dir = self.storage_root / session_id / dataset_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        # Stream to disk
        size = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = file_data.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    f.close()
                    dest_path.unlink(missing_ok=True)
                    raise ValueError(f"File too large (>{MAX_FILE_SIZE // (1024*1024)} MB)")
                f.write(chunk)

        # Read into pandas
        try:
            df = self._read_dataframe(str(dest_path), ext)
        except Exception as exc:
            dest_path.unlink(missing_ok=True)
            raise ValueError(f"Failed to parse file: {exc}") from exc

        columns = self._profile_columns(df)
        summary = self._generate_summary(df)
        sample_rows = self._extract_sample_rows(df)

        file_type = ext.lstrip(".")
        if file_type in ("xlsx", "xls"):
            file_type = "excel"

        return DatasetProfile(
            dataset_id=dataset_id,
            name=Path(filename).stem,
            file_path=str(dest_path),
            file_type=file_type,
            file_size_bytes=size,
            row_count=len(df),
            column_count=len(df.columns),
            columns=columns,
            summary=summary,
            sample_rows=sample_rows,
        )

    # ------------------------------------------------------------------
    # DataFrame loader
    # ------------------------------------------------------------------
    @staticmethod
    def _read_dataframe(path: str, ext: str):
        import pandas as pd

        if ext == ".csv":
            return pd.read_csv(path, nrows=100_000)
        elif ext == ".tsv":
            return pd.read_csv(path, sep="\t", nrows=100_000)
        elif ext in (".xlsx", ".xls"):
            return pd.read_excel(path, nrows=100_000)
        elif ext == ".json":
            return pd.read_json(path, lines=False, nrows=100_000)
        elif ext == ".jsonl":
            return pd.read_json(path, lines=True, nrows=100_000)
        elif ext == ".parquet":
            return pd.read_parquet(path)
        else:
            raise ValueError(f"No reader for {ext}")

    # ------------------------------------------------------------------
    # Column profiling
    # ------------------------------------------------------------------
    @staticmethod
    def _profile_columns(df) -> list[ColumnMeta]:
        import pandas as pd

        columns: list[ColumnMeta] = []
        for col in df.columns:
            series = df[col]
            dtype_str = str(series.dtype)
            null_count = int(series.isna().sum())
            unique_count = int(series.nunique())

            min_val = max_val = mean_val = None
            if pd.api.types.is_numeric_dtype(series):
                try:
                    min_val = str(series.min())
                    max_val = str(series.max())
                    mean_val = str(round(series.mean(), 4))
                except Exception:
                    pass
            elif pd.api.types.is_datetime64_any_dtype(series):
                try:
                    min_val = str(series.min())
                    max_val = str(series.max())
                except Exception:
                    pass

            # Sample values (top 5 non-null unique)
            sample = series.dropna().unique()[:SAMPLE_ROWS]
            sample_values = [str(v) for v in sample]

            columns.append(ColumnMeta(
                name=str(col),
                dtype=dtype_str,
                nullable=null_count > 0,
                unique_count=unique_count,
                null_count=null_count,
                min_value=min_val,
                max_value=max_val,
                mean_value=mean_val,
                sample_values=sample_values,
            ))
        return columns

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_summary(df) -> dict[str, Any]:
        import pandas as pd

        summary: dict[str, Any] = {
            "shape": list(df.shape),
            "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
            "memory_usage_bytes": int(df.memory_usage(deep=True).sum()),
            "missing_total": int(df.isna().sum().sum()),
        }

        # Numeric summary
        numeric_cols = df.select_dtypes(include="number")
        if not numeric_cols.empty:
            desc = numeric_cols.describe().round(4)
            summary["numeric_describe"] = {
                str(col): {str(k): float(v) if v == v else None for k, v in desc[col].items()}
                for col in desc.columns
            }

        # Categorical summary (top 3 value counts for object columns)
        cat_cols = df.select_dtypes(include=["object", "category"])
        if not cat_cols.empty:
            cat_summary = {}
            for col in cat_cols.columns[:10]:  # limit to 10 columns
                vc = df[col].value_counts().head(3)
                cat_summary[str(col)] = {str(k): int(v) for k, v in vc.items()}
            summary["categorical_top_values"] = cat_summary

        return summary

    # ------------------------------------------------------------------
    # Sample rows
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_sample_rows(df, n: int = SAMPLE_ROWS) -> list[dict[str, Any]]:
        sample = df.head(n)
        rows = []
        for _, row in sample.iterrows():
            rows.append({str(k): _safe_serialize(v) for k, v in row.items()})
        return rows

    # ------------------------------------------------------------------
    # Read dataset for analysis (returns a pandas DataFrame)
    # ------------------------------------------------------------------
    def load_dataframe(self, file_path: str):
        """Load a dataset file into a pandas DataFrame."""
        import pandas as pd

        ext = Path(file_path).suffix.lower()
        return self._read_dataframe(file_path, ext)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def delete_dataset_files(self, file_path: str) -> None:
        """Remove dataset files from disk."""
        p = Path(file_path)
        if p.exists():
            parent = p.parent
            p.unlink(missing_ok=True)
            # Remove the dataset directory if empty
            try:
                parent.rmdir()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Build context string for LLM injection
    # ------------------------------------------------------------------
    @staticmethod
    def build_dataset_context(
        name: str,
        schema_json: str | None,
        summary_json: str | None,
        sample_rows_json: str | None,
        row_count: int,
        column_count: int,
    ) -> str:
        """Build a text block describing a dataset for LLM prompt injection."""
        parts = [
            f"## Dataset: {name}",
            f"- Rows: {row_count:,}  Columns: {column_count}",
        ]

        if schema_json:
            try:
                schema = json.loads(schema_json)
                cols_desc = []
                for col in schema:
                    desc = f"  - `{col['name']}` ({col['dtype']})"
                    if col.get("null_count", 0) > 0:
                        desc += f" [{col['null_count']} nulls]"
                    if col.get("mean_value"):
                        desc += f" mean={col['mean_value']}"
                    cols_desc.append(desc)
                parts.append("- Columns:\n" + "\n".join(cols_desc))
            except (json.JSONDecodeError, KeyError):
                pass

        if summary_json:
            try:
                summary = json.loads(summary_json)
                if "numeric_describe" in summary:
                    parts.append(f"- Numeric stats: {json.dumps(summary['numeric_describe'], ensure_ascii=False)[:800]}")
                if "categorical_top_values" in summary:
                    parts.append(f"- Top categories: {json.dumps(summary['categorical_top_values'], ensure_ascii=False)[:600]}")
            except json.JSONDecodeError:
                pass

        if sample_rows_json:
            try:
                rows = json.loads(sample_rows_json)
                parts.append(f"- Sample rows (first {len(rows)}):")
                for i, row in enumerate(rows[:3]):
                    parts.append(f"  Row {i}: {json.dumps(row, ensure_ascii=False, default=str)[:300]}")
            except json.JSONDecodeError:
                pass

        return "\n".join(parts)


def _safe_serialize(v: Any) -> Any:
    """Convert pandas/numpy values to JSON-safe Python types."""
    import pandas as pd
    import numpy as np

    if v is None or (isinstance(v, float) and (v != v)):  # NaN check
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v
