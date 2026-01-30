from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RateInquiryRequest(BaseModel):
    """Request model for SMSA Rates API."""

    from_country: str = Field(..., alias="FromCountry")
    to_country: str = Field(..., alias="ToCountry")
    origin_city: str = Field(..., alias="OriginCity")
    destination_city: str = Field(..., alias="DestinationCity")
    weight: str = Field(..., alias="Weight")  # Must be string, not number
    pieces: str = Field(..., alias="Pieces")  # Must be string, not number
    service_type: Optional[str] = Field(default=None, alias="ServiceType")

    class Config:
        populate_by_name = True


class RateOption(BaseModel):
    """Single rate option from SMSA API response."""

    service_type: str = Field(..., alias="ServiceType")
    service_name: str = Field(..., alias="ServiceName")
    charge: str = Field(..., alias="Charge")
    currency: str = Field(..., alias="Currency")
    estimated_days: Optional[str] = Field(default=None, alias="EstimatedDays")

    class Config:
        populate_by_name = True


class RateInquiryResponse(BaseModel):
    """Response model from SMSA Rates API."""

    success: bool = Field(..., alias="Success")
    data: List[RateOption] = Field(default_factory=list, alias="Data")

    class Config:
        populate_by_name = True


class RateResult(BaseModel):
    """Formatted rate result for agent response."""

    success: bool
    rates: List[dict] = Field(default_factory=list)
    error_code: Optional[str] = Field(default=None, alias="errorCode")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")
