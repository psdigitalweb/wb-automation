"""Example of protected endpoint using JWT authentication."""

from fastapi import APIRouter, Depends
from app.deps import get_current_active_user, get_current_superuser

router = APIRouter(prefix="/api/v1/protected", tags=["protected"])


@router.get("/me")
async def get_my_info(current_user: dict = Depends(get_current_active_user)):
    """Example: Protected endpoint - requires authentication."""
    return {
        "message": "This is a protected endpoint",
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "email": current_user["email"],
        }
    }


@router.get("/admin")
async def admin_only(current_user: dict = Depends(get_current_superuser)):
    """Example: Admin-only endpoint - requires superuser."""
    return {
        "message": "This is an admin-only endpoint",
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "is_superuser": current_user["is_superuser"],
        }
    }

