"""Schemas Pydantic v2 para préstamos."""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from app.models.loan import LoanStatus, ReturnCondition


class LoanUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class LoanToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None


class LoanCreate(BaseModel):
    tool_id: int
    borrower_id: int
    due_date: date
    purpose: str | None = None
    notes: str | None = None
    signature_data: str | None = None  # firma digital táctil en base64 (dataURL)


class LoanReturnInput(BaseModel):
    return_condition: ReturnCondition
    notes: str | None = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int
    tool: LoanToolOut | None = None
    borrower_id: int
    borrower: LoanUserOut | None = None
    issued_by_id: int
    issued_by: LoanUserOut | None = None
    loan_date: datetime
    due_date: date
    return_date: datetime | None = None
    status: LoanStatus
    return_condition: ReturnCondition | None = None
    purpose: str | None = None
    notes: str | None = None
    voucher_pdf_url: str | None = None
    alert_sent: bool
