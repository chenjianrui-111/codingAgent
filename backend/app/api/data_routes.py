"""API routes for data agent operations.

Provides endpoints for:
- Dataset upload and management
- Data analysis via streaming agent
- Direct Python code execution
- Auto EDA pipeline
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.auth import get_auth_context_optional
from app.api.schemas import (
    DataAnalyzeRequest,
    DataAutoEDARequest,
    DataExecuteRequest,
    DataExecuteResponse,
    DatasetColumnInfo,
    DatasetDetailResponse,
    DatasetListItem,
    DatasetListResponse,
    DatasetUploadResponse,
)
from app.core.config import settings
from app.db import get_db
from app.models import DataAnalysisRunEntity, DatasetColumnEntity, DatasetEntity
from app.repositories.agent_repo import AgentRepository
from app.services.auth_service import AuthContext
from app.services.data_service import DataService

logger = logging.getLogger(__name__)

data_router = APIRouter(prefix="/data", tags=["data"])


# ---------------------------------------------------------------------------
# Upload dataset
# ---------------------------------------------------------------------------
@data_router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Upload a CSV/Excel/JSON/Parquet file for analysis."""
    repo = AgentRepository(db)
    session = repo.get_session_scoped(
        session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    data_service = DataService()

    try:
        profile = data_service.ingest_file(
            file_data=file.file,
            filename=file.filename,
            session_id=session_id,
            tenant_id=(auth_ctx.tenant_id if auth_ctx else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Persist to DB
    columns_json = json.dumps([
        {
            "name": c.name,
            "dtype": c.dtype,
            "nullable": c.nullable,
            "unique_count": c.unique_count,
            "null_count": c.null_count,
            "min_value": c.min_value,
            "max_value": c.max_value,
            "mean_value": c.mean_value,
            "sample_values": c.sample_values,
        }
        for c in profile.columns
    ], ensure_ascii=False)

    dataset = DatasetEntity(
        dataset_id=profile.dataset_id,
        session_id=session_id,
        tenant_id=(auth_ctx.tenant_id if auth_ctx else None),
        name=profile.name,
        file_path=profile.file_path,
        file_type=profile.file_type,
        file_size_bytes=profile.file_size_bytes,
        row_count=profile.row_count,
        column_count=profile.column_count,
        schema_json=columns_json,
        summary_json=json.dumps(profile.summary, ensure_ascii=False, default=str),
        sample_rows_json=json.dumps(profile.sample_rows, ensure_ascii=False, default=str),
        status="ready",
    )
    db.add(dataset)

    # Persist column metadata
    for col in profile.columns:
        db.add(DatasetColumnEntity(
            dataset_id=profile.dataset_id,
            column_name=col.name,
            dtype=col.dtype,
            nullable=col.nullable,
            unique_count=col.unique_count,
            null_count=col.null_count,
            min_value=col.min_value,
            max_value=col.max_value,
            mean_value=col.mean_value,
            sample_values_json=json.dumps(col.sample_values, ensure_ascii=False),
        ))

    db.commit()

    return DatasetUploadResponse(
        dataset_id=profile.dataset_id,
        name=profile.name,
        file_type=profile.file_type,
        file_size_bytes=profile.file_size_bytes,
        row_count=profile.row_count,
        column_count=profile.column_count,
        columns=[
            DatasetColumnInfo(
                name=c.name,
                dtype=c.dtype,
                nullable=c.nullable,
                unique_count=c.unique_count,
                null_count=c.null_count,
                min_value=c.min_value,
                max_value=c.max_value,
                mean_value=c.mean_value,
                sample_values=c.sample_values,
            )
            for c in profile.columns
        ],
        status="ready",
    )


# ---------------------------------------------------------------------------
# List datasets
# ---------------------------------------------------------------------------
@data_router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    session_id: str | None = None,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """List all datasets, optionally filtered by session."""
    query = db.query(DatasetEntity)

    if auth_ctx:
        query = query.filter(DatasetEntity.tenant_id == auth_ctx.tenant_id)
    if session_id:
        query = query.filter(DatasetEntity.session_id == session_id)

    datasets = query.order_by(DatasetEntity.created_at.desc()).all()

    return DatasetListResponse(
        datasets=[
            DatasetListItem(
                dataset_id=d.dataset_id,
                name=d.name,
                file_type=d.file_type,
                row_count=d.row_count,
                column_count=d.column_count,
                file_size_bytes=d.file_size_bytes,
                status=d.status,
                created_at=d.created_at,
            )
            for d in datasets
        ]
    )


# ---------------------------------------------------------------------------
# Get dataset detail
# ---------------------------------------------------------------------------
@data_router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    dataset_id: str,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Get detailed dataset information including schema and sample rows."""
    dataset = db.query(DatasetEntity).filter(DatasetEntity.dataset_id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")

    if auth_ctx and dataset.tenant_id and dataset.tenant_id != auth_ctx.tenant_id:
        raise HTTPException(status_code=403, detail="access denied")

    columns = []
    if dataset.schema_json:
        try:
            cols_data = json.loads(dataset.schema_json)
            columns = [DatasetColumnInfo(**c) for c in cols_data]
        except (json.JSONDecodeError, TypeError):
            pass

    summary = None
    if dataset.summary_json:
        try:
            summary = json.loads(dataset.summary_json)
        except json.JSONDecodeError:
            pass

    sample_rows = []
    if dataset.sample_rows_json:
        try:
            sample_rows = json.loads(dataset.sample_rows_json)
        except json.JSONDecodeError:
            pass

    return DatasetDetailResponse(
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        file_type=dataset.file_type,
        file_size_bytes=dataset.file_size_bytes,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        columns=columns,
        summary=summary,
        sample_rows=sample_rows,
        status=dataset.status,
        created_at=dataset.created_at,
    )


# ---------------------------------------------------------------------------
# Delete dataset
# ---------------------------------------------------------------------------
@data_router.delete("/datasets/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Delete a dataset and its files."""
    dataset = db.query(DatasetEntity).filter(DatasetEntity.dataset_id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")

    if auth_ctx and dataset.tenant_id and dataset.tenant_id != auth_ctx.tenant_id:
        raise HTTPException(status_code=403, detail="access denied")

    # Delete files
    DataService().delete_dataset_files(dataset.file_path)

    # Delete DB records (cascade will handle columns and analyses)
    db.delete(dataset)
    db.commit()

    return {"status": "deleted", "dataset_id": dataset_id}


# ---------------------------------------------------------------------------
# Execute Python code directly
# ---------------------------------------------------------------------------
@data_router.post("/execute", response_model=DataExecuteResponse)
async def execute_python(
    payload: DataExecuteRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Execute Python code in the session's stateful kernel."""
    from app.services.python_kernel_service import kernel_manager

    repo = AgentRepository(db)
    session = repo.get_session_scoped(
        payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    # If a dataset is specified, pre-load it
    if payload.dataset_id:
        dataset = db.query(DatasetEntity).filter(DatasetEntity.dataset_id == payload.dataset_id).first()
        if dataset:
            # Ensure df is loaded in the kernel
            load_code = _build_load_code(dataset)
            await kernel_manager.execute(payload.session_id, load_code)

    result = await kernel_manager.execute(payload.session_id, payload.code)

    return DataExecuteResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        display=result.display,
        figures=result.figures,
        execution_time_ms=result.execution_time_ms,
    )


# ---------------------------------------------------------------------------
# Data Analysis Agent (streaming)
# ---------------------------------------------------------------------------
@data_router.post("/analyze")
async def analyze_data(
    payload: DataAnalyzeRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Run the Data Analysis Agent with streaming output."""
    from app.services.data_agent_service import DataAgentRunner
    from app.services.agent_runner import StreamEvent
    from app.services.python_kernel_service import kernel_manager

    repo = AgentRepository(db)
    session = repo.get_session_scoped(
        payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    dataset = db.query(DatasetEntity).filter(DatasetEntity.dataset_id == payload.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")

    # Build dataset context for the LLM
    dataset_context = DataService.build_dataset_context(
        name=dataset.name,
        schema_json=dataset.schema_json,
        summary_json=dataset.summary_json,
        sample_rows_json=dataset.sample_rows_json,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
    )

    # Pre-load dataset into kernel
    load_code = _build_load_code(dataset)
    await kernel_manager.execute(payload.session_id, load_code)

    runner = DataAgentRunner()

    async def event_generator():
        try:
            async for event in runner.run_data_stream(
                session_id=payload.session_id,
                query=payload.query,
                dataset_context=dataset_context,
            ):
                yield f"data: {event.to_json()}\n\n"
        except Exception as exc:
            logger.exception("data analysis stream error")
            err = StreamEvent("error", {"message": str(exc)})
            yield f"data: {err.to_json()}\n\n"
            done = StreamEvent("done", {"run_id": "unknown", "status": "failed"})
            yield f"data: {done.to_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Auto EDA
# ---------------------------------------------------------------------------
@data_router.post("/auto-eda")
async def auto_eda(
    payload: DataAutoEDARequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Run automated Exploratory Data Analysis with streaming results."""
    from app.services.data_agent_service import AutoEDAService
    from app.services.agent_runner import StreamEvent

    repo = AgentRepository(db)
    session = repo.get_session_scoped(
        payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    dataset = db.query(DatasetEntity).filter(DatasetEntity.dataset_id == payload.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")

    eda_service = AutoEDAService()

    async def event_generator():
        try:
            yield f"data: {StreamEvent('status', {'message': 'Starting Auto EDA...'}).to_json()}\n\n"

            async for step_result in eda_service.run_eda(
                session_id=payload.session_id,
                file_path=dataset.file_path,
                file_type=dataset.file_type,
            ):
                # Emit step status
                status_message = f"Running: {step_result['description']}"
                yield f"data: {StreamEvent('status', {'message': status_message}).to_json()}\n\n"

                # Emit code
                yield f"data: {StreamEvent('eda_code', {'step': step_result['step'], 'code': step_result['code']}).to_json()}\n\n"

                # Emit results
                event_data = {
                    "step": step_result["step"],
                    "success": step_result["success"],
                    "stdout": step_result.get("stdout", ""),
                    "display": step_result.get("display"),
                    "execution_time_ms": step_result.get("execution_time_ms", 0),
                }
                if step_result.get("figures"):
                    event_data["figures"] = step_result["figures"]
                if not step_result["success"]:
                    event_data["stderr"] = step_result.get("stderr", "")

                yield f"data: {StreamEvent('eda_result', event_data).to_json()}\n\n"

            yield f"data: {StreamEvent('done', {'status': 'completed'}).to_json()}\n\n"

        except Exception as exc:
            logger.exception("auto EDA error")
            yield f"data: {StreamEvent('error', {'message': str(exc)}).to_json()}\n\n"
            yield f"data: {StreamEvent('done', {'status': 'failed'}).to_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_load_code(dataset: DatasetEntity) -> str:
    """Build Python code to load a dataset into the kernel as `df`."""
    read_func = "csv"
    if dataset.file_type in ("xlsx", "xls", "excel"):
        read_func = "excel"
    elif dataset.file_type == "json":
        read_func = "json"
    elif dataset.file_type == "parquet":
        read_func = "parquet"

    return f"""
import pandas as pd
import numpy as np
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    pass
try:
    import seaborn as sns
    sns.set_theme(style='whitegrid')
except ImportError:
    pass

df = pd.read_{read_func}('{dataset.file_path}')
print(f"Dataset loaded: {{df.shape[0]}} rows x {{df.shape[1]}} columns")
"""
