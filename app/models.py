from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, HttpUrl
from typing import Optional

class FeedIn(BaseModel):
    url: HttpUrl

class ItemOut(BaseModel):
    id: int
    title: Optional[str] = None
    url: str
    published: Optional[datetime] = None
    summary: Optional[str] = None