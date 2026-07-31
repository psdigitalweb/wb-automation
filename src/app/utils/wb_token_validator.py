"""Utility for validating Wildberries API tokens."""

import httpx
from typing import Tuple, Optional


def _response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return (response.text or "").strip()
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("errorText") or data.get("title")
        if detail:
            return str(detail)
    return (response.text or "").strip()


def _authorization_values(token: str) -> list[str]:
    raw_value = token.strip()
    if raw_value.lower().startswith("bearer "):
        stripped_token = raw_value[7:].strip()
    else:
        stripped_token = raw_value

    candidates = [
        f"Bearer {stripped_token}",
        stripped_token,
        raw_value,
    ]

    values: list[str] = []
    for value in candidates:
        if value and value not in values:
            values.append(value)
    return values


def _is_valid_status(status_code: int) -> bool:
    return status_code in (200, 429)


async def validate_wb_token(token: str) -> Tuple[bool, Optional[str]]:
    """Validate WB API token by making a minimal test request.
    
    Checks the Prices and Discounts endpoint first because it mirrors the
    application's WB prices ingestion. Then checks warehouses as a fallback.
    
    Args:
        token: WB API token to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if token is valid, False otherwise
        - error_message: Error message if validation failed, None if valid
    """
    if not token or token.strip() == "":
        return False, "Token is empty"
    
    if token.upper() == "MOCK":
        return False, "Token cannot be 'MOCK'"
    
    marketplace_base_url = "https://marketplace-api.wildberries.ru"
    timeout = 10
    
    # Try warehouses endpoint first (lightweight, minimal permissions)
    # Correct endpoint: GET /api/v3/warehouses (marketplace-api)
    warehouses_url = f"{marketplace_base_url}/api/v3/warehouses"
    prices_url = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            saw_unauthorized = False
            saw_forbidden = False
            auth_error_detail = None
            unexpected_status = None

            for authorization_value in _authorization_values(token):
                headers = {"Authorization": authorization_value}
                for url, params in (
                    (prices_url, {"limit": 1, "offset": 0}),
                    (warehouses_url, None),
                ):
                    try:
                        response = await client.get(url, headers=headers, params=params)
                    except httpx.TimeoutException:
                        return False, "Timeout connecting to WB API"
                    except Exception as e:
                        return False, f"Error validating token: {str(e)}"

                    if _is_valid_status(response.status_code):
                        return True, None
                    if response.status_code == 401:
                        saw_unauthorized = True
                        auth_error_detail = _response_detail(response) or auth_error_detail
                        continue
                    if response.status_code == 403:
                        saw_forbidden = True
                        auth_error_detail = _response_detail(response) or auth_error_detail
                        continue
                    unexpected_status = response.status_code

            if saw_forbidden:
                detail = f": {auth_error_detail}" if auth_error_detail else ""
                return False, f"Token lacks required permissions (403){detail}"
            if saw_unauthorized:
                detail = f": {auth_error_detail}" if auth_error_detail else ""
                return False, f"Invalid token: Unauthorized (401){detail}"
            if unexpected_status is not None:
                return False, f"Unexpected response: HTTP {unexpected_status}"
                
    except Exception as e:
        return False, f"Failed to validate token: {str(e)}"
    
    return False, "Validation failed: Unable to connect to WB API"

