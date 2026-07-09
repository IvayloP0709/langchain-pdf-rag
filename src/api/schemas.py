from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class IngestRequest(BaseModel):
    pdf_directory: str = Field(default="data/papers")
    md_directory: Optional[str] = Field(default=None)
    persist_directory: str = Field(default="./chroma_db")


class IngestResponse(BaseModel):
    status: str
    message: str
    persist_directory: str


class SourceBlock(BaseModel):
    source: str
    snippet: str
    rank: int
    page: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    persist_directory: str = Field(default="./chroma_db")


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceBlock]
    timing_ms: Optional[int] = None


class ChatRequest(BaseModel):
    message: str
    persist_directory: str = Field(default="./chroma_db")


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: List[SourceBlock]
    timing_ms: Optional[int] = None
