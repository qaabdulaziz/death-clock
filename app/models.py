"""Validated API request models."""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_of_birth: date | None = None
    life_expectancy_years: float | None = Field(default=None, gt=0, le=150)
    starting_balance: float | None = Field(default=None, ge=0, le=1e15)
    monthly_contribution: float | None = Field(default=None, ge=0, le=1e15)
    annual_return_rate: float | None = Field(default=None, ge=-100, le=100)
    currency: str | None = None
    setup_complete: bool | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter code")
        return normalized

    @field_validator(
        "life_expectancy_years",
        "starting_balance",
        "monthly_contribution",
        "annual_return_rate",
    )
    @classmethod
    def require_finite_numbers(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    cost: float = Field(ge=0, le=1e15)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("cost")
    @classmethod
    def require_finite_cost(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("cost must be finite")
        return value
