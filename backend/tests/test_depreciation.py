"""Pruebas del cálculo de depreciación (lineal y doble saldo decreciente)."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.tool import DepreciationMethod, Tool
from app.services.depreciation import calculate_current_value


def _tool(method, purchase_cost="1000", salvage="100", years=5, years_ago=2) -> Tool:
    return Tool(
        name="Herramienta de prueba",
        purchase_cost=Decimal(purchase_cost),
        salvage_value=Decimal(salvage),
        useful_life_years=years,
        purchase_date=date.today() - timedelta(days=365 * years_ago),
        depreciation_method=method,
    )


def test_lineal_depreciation_decreases_over_time():
    value = calculate_current_value(_tool(DepreciationMethod.lineal, years_ago=2))
    assert Decimal("100") <= value < Decimal("1000")


def test_lineal_depreciation_never_below_salvage():
    value = calculate_current_value(_tool(DepreciationMethod.lineal, years_ago=50))  # muy vieja
    assert value == Decimal("100.00")


def test_doble_saldo_depreciates_faster_than_lineal():
    lineal = calculate_current_value(_tool(DepreciationMethod.lineal, years_ago=2))
    doble = calculate_current_value(_tool(DepreciationMethod.doble_saldo, years_ago=2))
    assert doble < lineal


def test_returns_none_without_purchase_data():
    assert calculate_current_value(Tool(name="Sin datos")) is None
