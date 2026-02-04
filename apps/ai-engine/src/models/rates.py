from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RateInquiryRequest(BaseModel):
    """Request model for SMSA Rates API - matches actual API format."""

    fromCountry: str  # lowercase field name
    fromCity: str
    toCountry: str
    toCity: str
    documents: str = "documents"  # Required field, always "documents"
    productcategory: str = "Parcel"  # Required field, default "Parcel"
    weight: str  # Must be string, not number
    passkey: str  # Passkey in body (not header)
    language: str = "En"  # "En" or "Ar"

    class Config:
        populate_by_name = True


class RateOption(BaseModel):
    """Single rate option from SMSA API response - matches actual API format."""

    Product: str  # Service name (e.g., "SMSA Priority Parcels (SPOP)")
    Amount: float  # Base amount
    Currency: str  # Currency code (e.g., "SAR")
    VatAmount: float  # VAT amount
    ProductCode: str  # Service code (e.g., "DP", "SSB")
    TotalAmount: float  # Total including VAT
    VatPercentage: str  # VAT percentage (e.g., "15%")

    class Config:
        populate_by_name = True


class RateInquiryResponse(BaseModel):
    """Response model from SMSA Rates API - matches actual API format."""

    Success: bool
    Data: List[RateOption] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class RateResult(BaseModel):
    """Formatted rate result for agent response."""

    success: bool
    rates: List[dict] = Field(default_factory=list)
    error_code: Optional[str] = Field(default=None, alias="errorCode")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")
