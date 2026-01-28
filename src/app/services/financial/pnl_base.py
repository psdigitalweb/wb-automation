"""PnL base data provider (stub for future pnl_statement_snapshots integration).

This module provides an interface to get PnL base values for tax calculation.
Currently returns None (stub). Later will read from pnl_statement_snapshots.
"""

from __future__ import annotations

from typing import Dict, Optional


def get_pnl_base(project_id: int, period_id: int) -> Optional[Dict[str, float]]:
    """Get PnL base values for tax calculation.
    
    Args:
        project_id: Project ID
        period_id: Period ID
        
    Returns:
        Dict with keys:
        - operating_profit_net: Operating profit (net)
        - profit_before_tax_net: Profit before tax (net)
        - revenue_net: Revenue (net) - for turnover tax models
        
        Returns None if PnL data is not available (e.g., pnl_statement_snapshots not implemented yet).
    """
    # TODO: Implement reading from pnl_statement_snapshots table
    # For now, always return None (stub)
    return None
