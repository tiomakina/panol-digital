"""
Servicio de Depreciación — calcula el valor en libros actual de una herramienta.
Soporta los 3 métodos definidos en el modelo Tool: lineal, UOP y doble saldo decreciente.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from app.models.tool import DepreciationMethod, Tool


def _years_elapsed(purchase_date: date, as_of: date | None = None) -> Decimal:
    as_of = as_of or date.today()
    days = (as_of - purchase_date).days
    return Decimal(max(days, 0)) / Decimal("365.25")


def calculate_current_value(tool: Tool, as_of: date | None = None) -> Decimal | None:
    """
    Calcula el valor en libros actual según el método de depreciación de la herramienta.
    Devuelve None si no hay costo de compra o fecha de compra registrados.
    """
    if tool.purchase_cost is None or tool.purchase_date is None:
        return None

    cost = tool.purchase_cost
    salvage = tool.salvage_value or Decimal("0")
    life = Decimal(tool.useful_life_years or 1)
    years = _years_elapsed(tool.purchase_date, as_of)

    if life <= 0:
        return cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if tool.depreciation_method == DepreciationMethod.doble_saldo:
        # Doble saldo decreciente: cada año se deprecia el doble de la tasa lineal
        # sobre el valor remanente, sin bajar del valor de rescate.
        rate = Decimal("2") / life
        value = cost
        whole_years = int(years)
        for _ in range(whole_years):
            value = max(value - value * rate, salvage)
        fraction = years - whole_years
        if fraction > 0:
            value = max(value - value * rate * fraction, salvage)
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Lineal — y UOP como aproximación lineal mientras no se registren unidades de producción.
    annual_depreciation = (cost - salvage) / life
    depreciated = annual_depreciation * years
    value = max(cost - depreciated, salvage)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
