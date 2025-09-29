from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    sub: str = Field(..., description="Subject identifier")
    exp: datetime = Field(..., description="Expiration timestamp")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
