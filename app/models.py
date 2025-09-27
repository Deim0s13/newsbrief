from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List

class FeedIn(BaseModel):
    url: HttpUrl

class ItemOut(BaseModel):
    id: int
    title: Optional[str] = None
    url: str
    published: Optional[datetime] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_model: Optional[str] = None
    ai_generated_at: Optional[datetime] = None

class SummaryRequest(BaseModel):
    """Request to generate summary for specific item(s)."""
    item_ids: List[int] = Field(..., description="List of item IDs to summarize")
    model: Optional[str] = Field(None, description="Optional LLM model override")
    force_regenerate: bool = Field(False, description="Force regenerate even if summary exists")

class SummaryResponse(BaseModel):
    """Response from summary generation."""
    success: bool
    summaries_generated: int
    errors: int
    results: List['SummaryResultOut']

class SummaryResultOut(BaseModel):
    """Individual summary result."""
    item_id: int
    success: bool
    summary: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None

class LLMStatusOut(BaseModel):
    """LLM service status information."""
    available: bool
    base_url: str
    current_model: str
    models_available: List[str] = []
    error: Optional[str] = None

# Update forward references
SummaryResponse.model_rebuild()