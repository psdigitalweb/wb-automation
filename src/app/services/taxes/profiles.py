"""Registry and calculators for management tax estimates in Unit P&L."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Dict, Mapping


WB_UNIT_PNL_PROFILE_CODE = "wb_transfer_minus_vat_wb_cogs_tax"
USN_INCOME_PROFILE_CODE = "usn_income"
USN_INCOME_EXPENSES_PROFILE_CODE = "usn_income_expenses"
AUSN_INCOME_PROFILE_CODE = "ausn_income"
AUSN_INCOME_EXPENSES_PROFILE_CODE = "ausn_income_expenses"
OSNO_LLC_PROFILE_CODE = "osno_llc_profit"
NPD_PROFILE_CODE = "npd_income"


@dataclass(frozen=True)
class TaxProfileDefinition:
    model_code: str
    title: str
    short_title: str
    description: str
    formula: str
    base_kind: str
    tax_rate_label: str
    default_tax_percent: Decimal
    default_vat_percent: Decimal
    vat_options: tuple[Decimal, ...]
    supported_views: tuple[str, ...] = ("wildberries_unit_pnl",)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["default_tax_percent"] = float(self.default_tax_percent)
        result["default_vat_percent"] = float(self.default_vat_percent)
        result["vat_options"] = [float(value) for value in self.vat_options]
        result["supported_views"] = list(self.supported_views)
        return result


@dataclass(frozen=True)
class UnitPnlTaxInputs:
    sale_amount: Decimal
    transfer_for_goods: Decimal
    wb_total_signed: Decimal
    cogs_cost_total: Decimal
    profit_before_tax: Decimal


@dataclass(frozen=True)
class UnitPnlTaxResult:
    tax_base: Decimal
    vat_amount: Decimal
    primary_tax_amount: Decimal
    tax_expense_total: Decimal
    tax_rate: Decimal
    vat_rate: Decimal

    @property
    def profit_tax_amount(self) -> Decimal:
        """Compatibility name used by the Unit P&L response contract."""
        return self.primary_tax_amount


PROFILE_DEFINITIONS = (
    TaxProfileDefinition(
        model_code=WB_UNIT_PNL_PROFILE_CODE,
        title="По перечислению WB",
        short_title="Модель WB",
        description="Текущая управленческая модель проекта по данным финансового отчёта WB.",
        formula="(перечисление WB − НДС − расходы WB − себестоимость) × ставка",
        base_kind="wb_transfer",
        tax_rate_label="Ставка налога",
        default_tax_percent=Decimal("15"),
        default_vat_percent=Decimal("5"),
        vat_options=(Decimal("0"), Decimal("5"), Decimal("7"), Decimal("22")),
    ),
    TaxProfileDefinition(
        model_code=USN_INCOME_PROFILE_CODE,
        title="УСН «Доходы»",
        short_title="УСН",
        description="Оценка налога от полной выручки покупателей за выбранный период.",
        formula="(выручка − НДС) × ставка УСН",
        base_kind="revenue",
        tax_rate_label="Ставка УСН",
        default_tax_percent=Decimal("6"),
        default_vat_percent=Decimal("0"),
        vat_options=(Decimal("0"), Decimal("5"), Decimal("7"), Decimal("22")),
    ),
    TaxProfileDefinition(
        model_code=USN_INCOME_EXPENSES_PROFILE_CODE,
        title="УСН «Доходы минус расходы»",
        short_title="УСН Д−Р",
        description="Оценка от управленческой прибыли с учётом расходов, загруженных в Unit P&L.",
        formula="max(0, прибыль до налогов − НДС) × ставка УСН",
        base_kind="profit",
        tax_rate_label="Ставка УСН",
        default_tax_percent=Decimal("15"),
        default_vat_percent=Decimal("0"),
        vat_options=(Decimal("0"), Decimal("5"), Decimal("7"), Decimal("22")),
    ),
    TaxProfileDefinition(
        model_code=AUSN_INCOME_PROFILE_CODE,
        title="АУСН «Доходы»",
        short_title="АУСН",
        description="Управленческая оценка АУСН от выручки за выбранный период.",
        formula="выручка × ставка АУСН",
        base_kind="revenue",
        tax_rate_label="Ставка АУСН",
        default_tax_percent=Decimal("8"),
        default_vat_percent=Decimal("0"),
        vat_options=(Decimal("0"),),
    ),
    TaxProfileDefinition(
        model_code=AUSN_INCOME_EXPENSES_PROFILE_CODE,
        title="АУСН «Доходы минус расходы»",
        short_title="АУСН Д−Р",
        description="Оценка АУСН от положительной управленческой прибыли Unit P&L.",
        formula="max(0, прибыль до налогов) × ставка АУСН",
        base_kind="profit",
        tax_rate_label="Ставка АУСН",
        default_tax_percent=Decimal("20"),
        default_vat_percent=Decimal("0"),
        vat_options=(Decimal("0"),),
    ),
    TaxProfileDefinition(
        model_code=OSNO_LLC_PROFILE_CODE,
        title="ОСНО для ООО",
        short_title="ОСНО",
        description="Оценка НДС и налога на прибыль организации по данным Unit P&L.",
        formula="НДС + max(0, прибыль до налогов − НДС) × ставка налога на прибыль",
        base_kind="profit",
        tax_rate_label="Налог на прибыль",
        default_tax_percent=Decimal("25"),
        default_vat_percent=Decimal("22"),
        vat_options=(Decimal("10"), Decimal("22")),
    ),
    TaxProfileDefinition(
        model_code=NPD_PROFILE_CODE,
        title="НПД",
        short_title="НПД",
        description="Оценка налога самозанятого от выручки; только для допустимой деятельности.",
        formula="выручка × ставка НПД",
        base_kind="revenue",
        tax_rate_label="Ставка НПД",
        default_tax_percent=Decimal("4"),
        default_vat_percent=Decimal("0"),
        vat_options=(Decimal("0"),),
    ),
)

PROFILE_BY_CODE = {definition.model_code: definition for definition in PROFILE_DEFINITIONS}


def list_tax_profile_definitions() -> list[Dict[str, Any]]:
    """Return profiles available for project configuration."""
    return [definition.to_dict() for definition in PROFILE_DEFINITIONS]


def get_tax_profile_definition(model_code: str) -> TaxProfileDefinition | None:
    return PROFILE_BY_CODE.get(model_code)


def _parse_rate(params: Mapping[str, Any], key: str) -> Decimal:
    if key not in params:
        raise ValueError(f"Missing required tax profile parameter: {key}")
    try:
        value = Decimal(str(params[key]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Tax profile parameter '{key}' must be a number") from exc
    if not value.is_finite() or value < 0 or value > 1:
        raise ValueError(f"Tax profile parameter '{key}' must be between 0 and 1")
    return value


def coerce_tax_profile_params(params: object) -> Dict[str, Any]:
    if isinstance(params, Mapping):
        return dict(params)
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
        except json.JSONDecodeError as exc:
            raise ValueError("Tax profile params_json must contain valid JSON") from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise ValueError("Tax profile params_json must be an object")


def normalize_tax_profile_params(model_code: str, params: object) -> Dict[str, Any]:
    """Validate registered profile rates while preserving legacy API models."""
    normalized = coerce_tax_profile_params(params)
    if model_code not in PROFILE_BY_CODE:
        return normalized

    vat_rate = _parse_rate(normalized, "vat_rate")
    tax_rate = _parse_rate(normalized, "tax_rate")
    return {"vat_rate": str(vat_rate), "tax_rate": str(tax_rate)}


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def build_unit_pnl_tax_inputs(
    *,
    sale_amount: object,
    transfer_for_goods: object,
    wb_total_signed: object,
    cogs_cost_total: object,
    profit_before_tax: object,
) -> UnitPnlTaxInputs:
    return UnitPnlTaxInputs(
        sale_amount=_decimal(sale_amount),
        transfer_for_goods=_decimal(transfer_for_goods),
        wb_total_signed=_decimal(wb_total_signed),
        cogs_cost_total=_decimal(cogs_cost_total),
        profit_before_tax=_decimal(profit_before_tax),
    )


def calculate_unit_pnl_tax(
    *,
    model_code: str,
    params: object,
    inputs: UnitPnlTaxInputs,
) -> UnitPnlTaxResult:
    """Calculate a management tax estimate for one Unit P&L period."""
    definition = get_tax_profile_definition(model_code)
    if definition is None:
        raise ValueError(f"Tax profile '{model_code}' is not supported by Unit P&L")

    normalized = normalize_tax_profile_params(model_code, params)
    vat_rate = Decimal(normalized["vat_rate"])
    tax_rate = Decimal(normalized["tax_rate"])
    vat_amount = max(Decimal("0"), inputs.sale_amount) * vat_rate

    if definition.base_kind == "wb_transfer":
        tax_base = (
            inputs.transfer_for_goods
            - (max(Decimal("0"), inputs.transfer_for_goods) * vat_rate)
            - inputs.wb_total_signed
            - inputs.cogs_cost_total
        )
        vat_amount = max(Decimal("0"), inputs.transfer_for_goods) * vat_rate
    elif definition.base_kind == "revenue":
        tax_base = inputs.sale_amount - vat_amount
    else:
        tax_base = inputs.profit_before_tax - vat_amount

    primary_tax_amount = max(Decimal("0"), tax_base) * tax_rate
    tax_expense_total = primary_tax_amount
    if model_code != WB_UNIT_PNL_PROFILE_CODE:
        tax_expense_total += vat_amount
    return UnitPnlTaxResult(
        tax_base=tax_base,
        vat_amount=vat_amount,
        primary_tax_amount=primary_tax_amount,
        tax_expense_total=tax_expense_total,
        tax_rate=tax_rate,
        vat_rate=vat_rate,
    )


def calculate_wb_unit_pnl_tax(
    *,
    params: object,
    transfer_for_goods: object,
    wb_total_signed: object,
    cogs_cost_total: object,
) -> UnitPnlTaxResult:
    """Backward-compatible wrapper for the original profile unit tests."""
    inputs = build_unit_pnl_tax_inputs(
        sale_amount=0,
        transfer_for_goods=transfer_for_goods,
        wb_total_signed=wb_total_signed,
        cogs_cost_total=cogs_cost_total,
        profit_before_tax=0,
    )
    return calculate_unit_pnl_tax(
        model_code=WB_UNIT_PNL_PROFILE_CODE,
        params=params,
        inputs=inputs,
    )
