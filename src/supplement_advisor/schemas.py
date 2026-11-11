"""Public M1 input and guest result boundary."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

Status = Literal["queued", "running", "needs_input", "completed", "failed"]
AnalysisMode = Literal["collection", "evidence_review"]


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    product_name: str | None = Field(default=None, max_length=300)
    mode: AnalysisMode = "collection"

    @field_validator("url", "product_name")
    @classmethod
    def strip_input(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AnalysisAccepted(BaseModel):
    id: str
    access_token: str
    status: Status
    mode: AnalysisMode


class AnalysisResult(BaseModel):
    id: str
    status: Status
    mode: AnalysisMode
    product_name: str | None
    report: dict[str, Any] | None
    error_code: str | None
    message: str | None
    missing_fields: list[str] = Field(default_factory=list)
    supplemental_input_used: bool = False
    can_supplement: bool = False
    created_at: datetime
    updated_at: datetime


class SupplementalIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=150)
    amount: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    basis: str | None = Field(default=None, max_length=200)

    @field_validator("name", "amount", "unit", "basis")
    @classmethod
    def strip_values(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if info.field_name == "name" and not value:
            raise ValueError("ingredient values must not be blank")
        return value or None


class SupplementalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str | None = Field(default=None, max_length=300)
    manufacturer: str | None = Field(default=None, max_length=300)
    report_number: str | None = Field(default=None, max_length=100)
    ingredients: list[SupplementalIngredient] = Field(default_factory=list, max_length=50)

    @field_validator("product_name", "manufacturer", "report_number")
    @classmethod
    def strip_values(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("report_number")
    @classmethod
    def ascii_digits(cls, value: str | None) -> str | None:
        if value is not None and value and any(char not in "0123456789" for char in value):
            raise ValueError("report_number must contain ASCII digits")
        return value

    @model_validator(mode="after")
    def require_information(self):
        has_identity = any((self.product_name, self.manufacturer, self.report_number))
        has_ingredient = any(ingredient.name for ingredient in self.ingredients)
        if not has_identity and not has_ingredient:
            raise ValueError("at least one non-empty value is required")
        return self
