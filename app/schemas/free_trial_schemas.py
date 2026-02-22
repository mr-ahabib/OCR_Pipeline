"""Schemas for free trial functionality"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FreeTrialInfo(BaseModel):
    """Free trial usage information"""
    usage_count: int = Field(..., description="Number of times the free trial has been used")
    max_usage: int = Field(..., description="Maximum number of free trial uses allowed")
    remaining: int = Field(..., description="Number of remaining free trials")
    message: str = Field(..., description="Message about trial status")
    is_blocked: bool = Field(default=False, description="Whether the device is blocked")
    needs_cookie_consent: bool = Field(default=False, description="Whether cookie consent is needed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "usage_count": 1,
                "max_usage": 3,
                "remaining": 2,
                "message": "You have 2 free trials remaining.",
                "is_blocked": False,
                "needs_cookie_consent": False
            }
        }


class FreeTrialUserResponse(BaseModel):
    """Response model for free trial user"""
    id: int
    device_id: str
    usage_count: int
    max_usage: int
    remaining: int
    first_used_at: datetime
    last_used_at: Optional[datetime]
    is_blocked: bool
    
    class Config:
        from_attributes = True


class DeviceInfoRequest(BaseModel):
    """Request model containing device information"""
    device_id: Optional[str] = Field(None, description="Unique device identifier")
    cookie_id: Optional[str] = Field(None, description="Browser cookie ID")
    user_agent: Optional[str] = Field(None, description="Browser user agent string")
    
    class Config:
        json_schema_extra = {
            "example": {
                "device_id": "abc123xyz789",
                "cookie_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
            }
        }


class CookieConsentRequest(BaseModel):
    """Request model for cookie consent"""
    consent_given: bool = Field(..., description="Whether user accepted (True) or rejected (False) cookies")
    
    class Config:
        json_schema_extra = {
            "example": {
                "consent_given": True
            }
        }


class CookieConsentResponse(BaseModel):
    """Response model for cookie consent"""
    success: bool = Field(..., description="Whether the consent was successfully recorded")
    message: str = Field(..., description="Status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Cookie consent recorded successfully"
            }
        }
