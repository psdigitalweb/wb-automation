"""Utility for validating Wildberries API tokens."""

import httpx
from typing import Tuple, Optional


async def validate_wb_token(token: str) -> Tuple[bool, Optional[str]]:
    """Validate WB API token by making a minimal test request.
    
    Uses GET /api/v1/warehouses endpoint (lightweight, requires minimal permissions).
    If warehouses endpoint fails, tries GET /api/v2/list/goods/filter with limit=1.
    
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
    headers = {"Authorization": f"Bearer {token}"}
    timeout = 10
    
    # Try warehouses endpoint first (lightweight, minimal permissions)
    # Correct endpoint: GET /api/v3/warehouses (marketplace-api)
    warehouses_url = f"{marketplace_base_url}/api/v3/warehouses"
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try warehouses endpoint
            try:
                response = await client.get(warehouses_url, headers=headers)
                if response.status_code == 200:
                    return True, None  # Token is valid
                elif response.status_code == 401:
                    return False, "Invalid token: Unauthorized (401)"
                elif response.status_code == 403:
                    return False, "Token lacks required permissions (403)"
                elif response.status_code == 429:
                    # Rate limit is OK - means token is valid
                    return True, None
                else:
                    # Try alternative endpoint as fallback
                    pass
            except httpx.TimeoutException:
                return False, "Timeout connecting to WB API"
            except Exception as e:
                # Fallback to alternative endpoint
                pass
            
            # Fallback: Try prices endpoint with minimal request
            prices_url = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
            try:
                response = await client.get(prices_url, headers=headers, params={"limit": 1, "offset": 0})
                if response.status_code == 200:
                    return True, None
                elif response.status_code == 401:
                    return False, "Invalid token: Unauthorized (401)"
                elif response.status_code == 403:
                    return False, "Token lacks required permissions (403)"
                elif response.status_code == 429:
                    return True, None  # Rate limit means token is valid
                else:
                    return False, f"Unexpected response: HTTP {response.status_code}"
            except httpx.TimeoutException:
                return False, "Timeout connecting to WB API"
            except Exception as e:
                return False, f"Error validating token: {str(e)}"
                
    except Exception as e:
        return False, f"Failed to validate token: {str(e)}"
    
    return False, "Validation failed: Unable to connect to WB API"

