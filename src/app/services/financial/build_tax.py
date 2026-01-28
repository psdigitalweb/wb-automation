"""Build tax statement service.

Calculates tax expense based on tax profile and PnL base data,
creates materialized tax_statement_snapshots.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.db_taxes import (
    create_tax_statement_snapshot,
    get_tax_adjustments_sum,
    get_tax_profile,
)
from app.services.financial.pnl_base import get_pnl_base


CALC_VERSION = "1.0"


class ProfitTaxModel:
    """Profit tax model: tax = max(0, base) * rate."""
    
    @staticmethod
    def calculate(base: Decimal, rate: Decimal) -> Decimal:
        """Calculate tax from base and rate.
        
        Args:
            base: Tax base (profit before tax or operating profit)
            rate: Tax rate (e.g., 0.20 for 20%)
            
        Returns:
            Tax amount
        """
        return max(Decimal("0"), base) * rate


class TurnoverTaxModel:
    """Turnover tax model: tax = revenue_net * rate."""
    
    @staticmethod
    def calculate(revenue: Decimal, rate: Decimal) -> Decimal:
        """Calculate tax from revenue and rate.
        
        Args:
            revenue: Revenue (net)
            rate: Tax rate (e.g., 0.06 for 6%)
            
        Returns:
            Tax amount
        """
        return max(Decimal("0"), revenue) * rate


def build_tax_statement(
    project_id: int,
    period_id: int,
    run_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build tax statement snapshot for a project and period.
    
    Args:
        project_id: Project ID
        period_id: Period ID
        run_id: Optional ingest run ID for tracking
        
    Returns:
        Dict with stats_json structure:
        - ok: bool
        - project_id, period_id
        - model_code, rate, base_value
        - computed_tax, adjustments_sum (if applicable)
        - tax_expense_total
        - warnings: []
        - calc_version
    """
    warnings: List[str] = []
    
    # 1. Load tax profile
    tax_profile = get_tax_profile(project_id)
    if not tax_profile:
        return {
            "ok": False,
            "reason": "tax_profile_missing",
            "project_id": project_id,
            "period_id": period_id,
            "warnings": warnings,
        }
    
    model_code = tax_profile["model_code"]
    params = tax_profile["params_json"]
    
    # 2. Load PnL base (stub - returns None for now)
    pnl_base = get_pnl_base(project_id, period_id)
    if not pnl_base:
        return {
            "ok": False,
            "reason": "pnl_missing",
            "project_id": project_id,
            "period_id": period_id,
            "model_code": model_code,
            "warnings": ["PnL data not available. pnl_statement_snapshots not implemented yet."],
        }
    
    # 3. Apply tax model
    rate = Decimal(str(params.get("rate", 0)))
    base_key = params.get("base_key", "profit_before_tax_net")
    
    computed_tax: Optional[Decimal] = None
    base_value: Optional[Decimal] = None
    
    if model_code == "profit_tax":
        # Get base from PnL
        if base_key == "profit_before_tax_net":
            base_value = Decimal(str(pnl_base.get("profit_before_tax_net", 0)))
        elif base_key == "operating_profit_net":
            base_value = Decimal(str(pnl_base.get("operating_profit_net", 0)))
        else:
            warnings.append(f"Unknown base_key '{base_key}', using profit_before_tax_net")
            base_value = Decimal(str(pnl_base.get("profit_before_tax_net", 0)))
        
        computed_tax = ProfitTaxModel.calculate(base_value, rate)
    
    elif model_code == "turnover_tax":
        revenue_net = Decimal(str(pnl_base.get("revenue_net", 0)))
        base_value = revenue_net
        computed_tax = TurnoverTaxModel.calculate(revenue_net, rate)
    
    else:
        return {
            "ok": False,
            "reason": "unknown_model_code",
            "project_id": project_id,
            "period_id": period_id,
            "model_code": model_code,
            "warnings": [f"Unknown tax model code: {model_code}"],
        }
    
    # 4. Get adjustments sum (optional - table might not exist)
    adjustments_sum = get_tax_adjustments_sum(project_id, period_id)
    tax_expense_total = computed_tax + adjustments_sum
    
    # 5. Prepare stats_json
    stats_json: Dict[str, Any] = {
        "ok": True,
        "project_id": project_id,
        "period_id": period_id,
        "model_code": model_code,
        "rate": float(rate),
        "base_value": float(base_value) if base_value is not None else None,
        "base_key": base_key,
        "computed_tax": float(computed_tax) if computed_tax is not None else None,
        "adjustments_sum": float(adjustments_sum),
        "tax_expense_total": float(tax_expense_total),
        "warnings": warnings,
        "calc_version": CALC_VERSION,
        # Snapshot of tax profile for audit
        "tax_profile_snapshot": {
            "model_code": model_code,
            "params": params,
        },
    }
    
    # 6. Create snapshot
    try:
        snapshot = create_tax_statement_snapshot(
            project_id=project_id,
            period_id=period_id,
            status="success",
            tax_expense_total=tax_expense_total,
            breakdown_json={},  # Can be extended later
            stats_json=stats_json,
            error_message=None,
            error_trace=None,
        )
        
        stats_json["snapshot_id"] = snapshot["id"]
        stats_json["snapshot_version"] = snapshot["version"]
        
        return stats_json
    
    except Exception as exc:
        # Create failed snapshot
        error_message = str(exc)
        error_trace = f"{type(exc).__name__}: {error_message}"
        
        try:
            create_tax_statement_snapshot(
                project_id=project_id,
                period_id=period_id,
                status="failed",
                tax_expense_total=None,
                breakdown_json={},
                stats_json={
                    "ok": False,
                    "project_id": project_id,
                    "period_id": period_id,
                    "model_code": model_code,
                    "error": error_message,
                    "calc_version": CALC_VERSION,
                },
                error_message=error_message,
                error_trace=error_trace,
            )
        except Exception:
            pass  # If snapshot creation fails, at least return error stats
        
        return {
            "ok": False,
            "reason": "snapshot_creation_failed",
            "project_id": project_id,
            "period_id": period_id,
            "model_code": model_code,
            "error": error_message,
            "warnings": warnings,
        }
