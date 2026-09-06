from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Citation(BaseModel):
    """Pointer back to the source document. Quotes must be verbatim."""

    document_id: str
    page: int | None = None
    section: str | None = None
    quote: str
    start_char: int | None = None
    end_char: int | None = None
