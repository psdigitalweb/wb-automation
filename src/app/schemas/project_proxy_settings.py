"""Pydantic schemas for project proxy settings."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProjectProxySettingsResponse(BaseModel):
    enabled: bool
    scheme: str
    host: str
    port: int
    username: Optional[str] = None
    rotate_mode: str
    test_url: str
    last_test_at: Optional[datetime] = None
    last_test_ok: Optional[bool] = None
    last_test_error: Optional[str] = None
    password_set: bool = Field(..., description="True if an encrypted password exists (password is never returned)")


class ProjectProxySettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    scheme: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    rotate_mode: Optional[str] = None
    test_url: Optional[str] = None

    @field_validator("scheme")
    @classmethod
    def validate_scheme(cls, v: Optional[str]):
        if v is None:
            return v
        vv = str(v).strip().lower()
        if vv not in ("http", "https"):
            raise ValueError("scheme must be 'http' or 'https'")
        return vv

    @field_validator("rotate_mode")
    @classmethod
    def validate_rotate_mode(cls, v: Optional[str]):
        if v is None:
            return v
        vv = str(v).strip().lower()
        if vv != "fixed":
            raise ValueError("rotate_mode must be 'fixed'")
        return vv

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: Optional[str]):
        if v is None:
            return v
        if any(ch.isspace() for ch in str(v)):
            raise ValueError("host must not contain whitespace")
        return str(v).strip()

    @field_validator("test_url")
    @classmethod
    def validate_test_url(cls, v: Optional[str]):
        if v is None:
            return v
        vv = str(v).strip()
        if not vv:
            raise ValueError("test_url cannot be empty")
        if any(ch.isspace() for ch in vv):
            raise ValueError("test_url must not contain whitespace")
        return vv


class ProjectProxyTestResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    status_code: Optional[int] = None
    elapsed_ms: Optional[int] = None

