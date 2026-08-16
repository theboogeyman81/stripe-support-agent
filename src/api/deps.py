"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException, Request


def check_admin_key(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Validate the X-Admin-Key header against settings."""
    if x_admin_key is None:
        raise HTTPException(status_code=401, detail="missing admin key")
    if x_admin_key != request.app.state.settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin key")
