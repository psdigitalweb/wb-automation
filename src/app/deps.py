"""Dependencies for FastAPI endpoints."""

from typing import Optional, List
from fastapi import Depends, HTTPException, status, Path, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import decode_token
from app.db_users import get_user_by_id, get_user_by_username
from app.db_projects import get_project_member, ProjectRole
from app.schemas.auth import TokenData

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Get current user from JWT access token."""
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:14","message":"get_current_user entry","data":{"has_token":bool(credentials.credentials)},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:26","message":"Decoding token","timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    payload = decode_token(token, token_type="access")
    
    if payload is None:
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:32","message":"Token decode returned None","timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        raise credentials_exception
    
    username: Optional[str] = payload.get("sub")
    user_id: Optional[int] = payload.get("user_id")
    
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:40","message":"Token decoded","data":{"username":username,"user_id":user_id},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    
    if username is None and user_id is None:
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:44","message":"Both username and user_id are None","timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        raise credentials_exception
    
    # Try to get user by username first, then by ID
    user = None
    if username:
        user = get_user_by_username(username)
    if not user and user_id:
        user = get_user_by_id(user_id)
    
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:52","message":"User lookup result","data":{"found":user is not None,"user_id":user.get("id") if user else None},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    
    if user is None:
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:56","message":"User not found","timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        raise credentials_exception
    
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:64","message":"get_current_user exit","data":{"user_id":user.get("id")},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    return user


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current active user."""
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:50","message":"get_current_active_user entry","data":{"user_id":current_user.get("id"),"username":current_user.get("username"),"is_active":current_user.get("is_active")},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    if not current_user.get("is_active"):
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:54","message":"User is inactive","data":{"user_id":current_user.get("id")},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"deps-auth","hypothesisId":"H3","location":"deps.py:59","message":"get_current_active_user exit","data":{"user_id":current_user.get("id")},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    return current_user


async def get_current_superuser(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Get current superuser."""
    if not current_user.get("is_superuser"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


async def get_project_membership(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Verify that current user is a member of the project.
    
    Returns project member info with role.
    Raises 404 if project doesn't exist or user is not a member.
    """
    member = get_project_member(project_id, current_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member"
        )
    return member


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[dict]:
    """Get current user from JWT if Authorization header present, else None."""
    if not credentials:
        return None
    payload = decode_token(credentials.credentials, token_type="access")
    if payload is None:
        return None
    username = payload.get("sub")
    user_id = payload.get("user_id")
    if username is None and user_id is None:
        return None
    user = None
    if username:
        user = get_user_by_username(username)
    if not user and user_id:
        user = get_user_by_id(user_id)
    return user


def _allow_client_portal_read(
    request: Request,
    project_id: int,
    optional_user: Optional[dict],
) -> dict:
    """Allow read-only access for client portal (Host=reports.zakka.ru, project_id=1) without JWT.
    Otherwise require valid user and project membership."""
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    client_portal = host == "reports.zakka.ru"
    if client_portal and project_id == 1:
        return {"allowed": True, "client_portal": True}
    if optional_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not optional_user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    member = get_project_member(project_id, optional_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member",
        )
    return {"allowed": True, "user": optional_user, "membership": member}


async def allow_client_portal_read(
    request: Request,
    project_id: int = Path(..., description="Project ID"),
    optional_user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    """Dependency: allow read for client portal (reports.zakka.ru + project 1) without JWT, else require auth."""
    return _allow_client_portal_read(request, project_id, optional_user)


async def require_project_role(
    required_roles: List[str],
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to have one of the specified roles in the project.
    
    Args:
        required_roles: List of allowed roles (e.g., ['owner', 'admin'])
    
    Returns project member info with role.
    Raises 403 if user doesn't have required role.
    """
    member = get_project_member(project_id, current_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member"
        )
    
    if member["role"] not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required role: {', '.join(required_roles)}. Your role: {member['role']}"
        )
    
    return member


# Convenience dependencies for common role checks
async def require_project_owner(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project owner."""
    return await require_project_role([ProjectRole.OWNER], project_id, current_user)


async def require_project_admin(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project owner or admin."""
    return await require_project_role([ProjectRole.OWNER, ProjectRole.ADMIN], project_id, current_user)


async def require_project_member(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project member (any role except viewer)."""
    return await require_project_role(
        [ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER],
        project_id,
        current_user
    )

