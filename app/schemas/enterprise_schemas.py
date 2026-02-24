"""Enterprise OCR Pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from enum import Enum


class EnterprisePaymentStatus(str, Enum):
    PAID         = "paid"
    PARTIAL_PAID = "partial_paid"
    DUE          = "due"


class EnterpriseCreate(BaseModel):
    name:           str            = Field(..., min_length=1, max_length=255,
                                          description="Enterprise / client name")
    phone:          Optional[str]  = Field(None, max_length=50)
    email:          Optional[EmailStr] = None
    description:    Optional[str]  = None

    total_pages:    int            = Field(..., ge=1, description="Pages quota allocated")
    unit_price:     float          = Field(10.0, ge=0, description="Price per page in BDT")

    start_date:     Optional[date] = None
    end_date:       Optional[date] = None

    advance_bill:   float          = Field(0.0, ge=0, description="Amount paid in advance")
    no_of_documents: int           = Field(0,  ge=0,  description="Expected number of documents")

    payment_status: EnterprisePaymentStatus = EnterprisePaymentStatus.DUE

    @model_validator(mode="after")
    def validate_dates_and_billing(self) -> "EnterpriseCreate":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        total_cost = self.total_pages * self.unit_price
        if self.advance_bill > total_cost:
            raise ValueError(
                f"advance_bill ({self.advance_bill}) cannot exceed total cost ({total_cost})"
            )
        return self


class EnterpriseUpdate(BaseModel):
    """All fields are optional — only provided fields are updated."""
    name:            Optional[str]   = Field(None, min_length=1, max_length=255)
    phone:           Optional[str]   = Field(None, max_length=50)
    email:           Optional[EmailStr] = None
    description:     Optional[str]  = None

    total_pages:     Optional[int]  = Field(None, ge=1)
    unit_price:      Optional[float] = Field(None, ge=0)

    start_date:      Optional[date] = None
    end_date:        Optional[date] = None

    advance_bill:    Optional[float] = Field(None, ge=0)
    no_of_documents: Optional[int]  = Field(None, ge=0)

    payment_status:  Optional[EnterprisePaymentStatus] = None


class EnterprisePaymentStatusUpdate(BaseModel):
    payment_status: EnterprisePaymentStatus
    advance_bill:   Optional[float] = Field(None, ge=0,
                                            description="Update advance amount at the same time")


class EnterpriseResponse(BaseModel):
    id:              int
    name:            str
    phone:           Optional[str]
    email:           Optional[str]
    description:     Optional[str]

    total_pages:     int
    unit_price:      float
    total_cost:      float

    start_date:      Optional[date]
    end_date:        Optional[date]
    duration_days:   Optional[int]

    advance_bill:    float
    due_amount:      float
    payment_status:  EnterprisePaymentStatus

    no_of_documents: int
    pages_used:      int
    pages_remaining: int            = Field(..., description="total_pages − pages_used")

    created_by:      int            = Field(..., description="User ID of the admin who created this")
    created_by_name: Optional[str]  = Field(None, description="Full name of creator (populated by service)")

    is_deleted:      bool
    created_at:      datetime
    updated_at:      Optional[datetime]

    class Config:
        from_attributes = True


class EnterpriseListResponse(BaseModel):
    total:       int
    enterprises: List[EnterpriseResponse]


class EnterpriseOCRDocumentCreate(BaseModel):
    enterprise_id:  int
    processed_by:   int
    filename:       str
    file_path:      Optional[str] = None
    file_type:      str
    file_size:      int
    ocr_mode:       str
    ocr_engine:     str
    languages:      List[str]
    extracted_text: str
    confidence:     float
    total_pages:    int  = 1
    pages_data:     Optional[List[Dict[str, Any]]] = None
    processing_time: Optional[float] = None
    character_count: Optional[int]   = None


class EnterpriseOCRDocumentResponse(BaseModel):
    id:             int
    enterprise_id:  int
    processed_by:   int
    processor_name: Optional[str] = Field(None, description="Full name of the processor")

    filename:       str
    file_type:      str
    file_size:      int
    ocr_mode:       str
    ocr_engine:     str
    languages:      List[str]

    extracted_text: str
    confidence:     float
    total_pages:    int
    pages_data:     Optional[List[Dict[str, Any]]]
    processing_time: Optional[float]
    character_count: Optional[int]

    created_at:     datetime

    class Config:
        from_attributes = True


class EnterpriseOCRHistoryResponse(BaseModel):
    total:     int
    documents: List[EnterpriseOCRDocumentResponse]

class EnterpriseBillingSummary(BaseModel):
    total_enterprises:    int
    total_pages_allocated: int
    total_cost:           float
    total_advance_billed: float
    total_due_amount:     float
    paid_count:           int
    partial_paid_count:   int
    due_count:            int
