"""Pydantic schemas for the traces / observations endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UsageDetail(BaseModel):
    input: int | None = None
    output: int | None = None
    total: int | None = None
    unit: str | None = None


class ObservationSummary(BaseModel):
    id: str
    trace_id: str = Field(alias="traceId")
    name: str | None = None
    type: str | None = None
    model: str | None = None
    start_time: datetime | None = Field(None, alias="startTime")
    end_time: datetime | None = Field(None, alias="endTime")
    latency_ms: float | None = None
    usage: UsageDetail | None = None
    input: Any | None = None
    output: Any | None = None
    status_message: str | None = Field(None, alias="statusMessage")
    level: str | None = None

    model_config = {"populate_by_name": True}


class TraceSummary(BaseModel):
    id: str
    name: str | None = None
    user_id: str | None = Field(None, alias="userId")
    timestamp: datetime | None = None
    tags: list[str] = []
    metadata: dict[str, Any] | None = None
    input: Any | None = None
    output: Any | None = None
    latency: float | None = None
    total_cost: float | None = Field(None, alias="totalCost")
    observations: list[str] | None = None

    model_config = {"populate_by_name": True}


class TraceDetail(TraceSummary):
    """Full trace including nested observations."""
    observations_detail: list[ObservationSummary] = Field(
        default_factory=list, alias="observations"
    )


class TraceListResponse(BaseModel):
    data: list[TraceSummary]
    meta: dict[str, Any] = {}


class ObservationListResponse(BaseModel):
    data: list[ObservationSummary]
    meta: dict[str, Any] = {}
