"""
Production-ready HTTP Response Codes and Messages
Centralized response handling for consistent API responses
"""
from typing import Any, Dict, Optional
from fastapi import status


class ResponseCode:
    """HTTP Response Code Container"""
    def __init__(self, code: int, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code


class SuccessCode:
    """Success Response Codes (2xx)"""
    
    # 200 - Success
    OK = ResponseCode(
        code=200,
        message="Request processed successfully",
        status_code=status.HTTP_200_OK
    )
    
    RETRIEVED = ResponseCode(
        code=2001,
        message="Data retrieved successfully",
        status_code=status.HTTP_200_OK
    )
    
    UPDATED = ResponseCode(
        code=2002,
        message="Resource updated successfully",
        status_code=status.HTTP_200_OK
    )
    
    DELETED = ResponseCode(
        code=2003,
        message="Resource deleted successfully",
        status_code=status.HTTP_200_OK
    )
    
    # 201 - Created
    CREATED = ResponseCode(
        code=201,
        message="Resource created successfully",
        status_code=status.HTTP_201_CREATED
    )
    
    USER_REGISTERED = ResponseCode(
        code=2011,
        message="User registered successfully",
        status_code=status.HTTP_201_CREATED
    )
    
    DOCUMENT_CREATED = ResponseCode(
        code=2012,
        message="Document created successfully",
        status_code=status.HTTP_201_CREATED
    )
    
    # 202 - Accepted
    ACCEPTED = ResponseCode(
        code=202,
        message="Request accepted for processing",
        status_code=status.HTTP_202_ACCEPTED
    )
    
    PROCESSING = ResponseCode(
        code=2021,
        message="Request is being processed",
        status_code=status.HTTP_202_ACCEPTED
    )
    
    # 204 - No Content
    NO_CONTENT = ResponseCode(
        code=204,
        message="Request successful but no content to return",
        status_code=status.HTTP_204_NO_CONTENT
    )


class ErrorCode:
    """Error Response Codes (4xx, 5xx)"""
    
    # 400 - Bad Request
    BAD_REQUEST = ResponseCode(
        code=400,
        message="Bad request",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    INVALID_INPUT = ResponseCode(
        code=4001,
        message="Invalid input provided",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    INVALID_FILE_TYPE = ResponseCode(
        code=4002,
        message="Invalid file type",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    FILE_TOO_LARGE = ResponseCode(
        code=4003,
        message="File size exceeds maximum limit",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    MISSING_REQUIRED_FIELD = ResponseCode(
        code=4004,
        message="Missing required field",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    INVALID_DATE_FORMAT = ResponseCode(
        code=4005,
        message="Invalid date format",
        status_code=status.HTTP_400_BAD_REQUEST
    )
    
    # 401 - Unauthorized
    UNAUTHORIZED = ResponseCode(
        code=401,
        message="Authentication required",
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    INVALID_CREDENTIALS = ResponseCode(
        code=4011,
        message="Invalid username or password",
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    TOKEN_EXPIRED = ResponseCode(
        code=4012,
        message="Authentication token has expired",
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    INVALID_TOKEN = ResponseCode(
        code=4013,
        message="Invalid authentication token",
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    SESSION_EXPIRED = ResponseCode(
        code=4014,
        message="Session has expired",
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    # 403 - Forbidden
    FORBIDDEN = ResponseCode(
        code=403,
        message="Access forbidden",
        status_code=status.HTTP_403_FORBIDDEN
    )
    
    INSUFFICIENT_PERMISSIONS = ResponseCode(
        code=4031,
        message="Insufficient permissions to perform this action",
        status_code=status.HTTP_403_FORBIDDEN
    )
    
    ACCOUNT_DISABLED = ResponseCode(
        code=4032,
        message="Account is disabled",
        status_code=status.HTTP_403_FORBIDDEN
    )
    
    ACCESS_DENIED = ResponseCode(
        code=4033,
        message="Access denied to this resource",
        status_code=status.HTTP_403_FORBIDDEN
    )
    
    # 404 - Not Found
    NOT_FOUND = ResponseCode(
        code=404,
        message="Resource not found",
        status_code=status.HTTP_404_NOT_FOUND
    )
    
    USER_NOT_FOUND = ResponseCode(
        code=4041,
        message="User not found",
        status_code=status.HTTP_404_NOT_FOUND
    )
    
    DOCUMENT_NOT_FOUND = ResponseCode(
        code=4042,
        message="Document not found",
        status_code=status.HTTP_404_NOT_FOUND
    )
    
    ENDPOINT_NOT_FOUND = ResponseCode(
        code=4043,
        message="Endpoint not found",
        status_code=status.HTTP_404_NOT_FOUND
    )
    
    # 409 - Conflict
    CONFLICT = ResponseCode(
        code=409,
        message="Resource conflict",
        status_code=status.HTTP_409_CONFLICT
    )
    
    USERNAME_EXISTS = ResponseCode(
        code=4091,
        message="Username already exists",
        status_code=status.HTTP_409_CONFLICT
    )
    
    EMAIL_EXISTS = ResponseCode(
        code=4092,
        message="Email already exists",
        status_code=status.HTTP_409_CONFLICT
    )
    
    DUPLICATE_ENTRY = ResponseCode(
        code=4093,
        message="Duplicate entry detected",
        status_code=status.HTTP_409_CONFLICT
    )
    
    # 422 - Unprocessable Entity
    VALIDATION_ERROR = ResponseCode(
        code=422,
        message="Validation error",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    
    WEAK_PASSWORD = ResponseCode(
        code=4221,
        message="Password does not meet strength requirements",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    
    INVALID_EMAIL = ResponseCode(
        code=4222,
        message="Invalid email format",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    
    INVALID_USERNAME = ResponseCode(
        code=4223,
        message="Invalid username format",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    
    # 429 - Too Many Requests
    RATE_LIMIT_EXCEEDED = ResponseCode(
        code=429,
        message="Rate limit exceeded",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS
    )
    
    # 500 - Internal Server Error
    INTERNAL_ERROR = ResponseCode(
        code=500,
        message="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    DATABASE_ERROR = ResponseCode(
        code=5001,
        message="Database operation failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    OCR_PROCESSING_ERROR = ResponseCode(
        code=5002,
        message="OCR processing failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    FILE_PROCESSING_ERROR = ResponseCode(
        code=5003,
        message="File processing failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    EXTERNAL_API_ERROR = ResponseCode(
        code=5004,
        message="External API call failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    # 503 - Service Unavailable
    SERVICE_UNAVAILABLE = ResponseCode(
        code=503,
        message="Service temporarily unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    DATABASE_UNAVAILABLE = ResponseCode(
        code=5031,
        message="Database service unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    MAINTENANCE_MODE = ResponseCode(
        code=5032,
        message="Service under maintenance",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )


def success_response(
    code: ResponseCode = SuccessCode.OK,
    data: Any = None,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized success response
    
    Args:
        code: ResponseCode object
        data: Response data
        message: Optional custom message
    
    Returns:
        Standardized response dictionary
    """
    return {
        "success": True,
        "code": code.code,
        "message": message or code.message,
        "data": data
    }


def error_response(
    code: ResponseCode = ErrorCode.INTERNAL_ERROR,
    message: Optional[str] = None,
    errors: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response
    
    Args:
        code: ResponseCode object
        message: Optional custom message
        errors: Optional detailed error information
    
    Returns:
        Standardized error response dictionary
    """
    response = {
        "success": False,
        "code": code.code,
        "message": message or code.message
    }
    
    if errors:
        response["errors"] = errors
    
    return response


def paginated_response(
    data: list,
    total: int,
    page: int,
    page_size: int,
    code: ResponseCode = SuccessCode.RETRIEVED,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized paginated response
    
    Args:
        data: List of items
        total: Total number of items
        page: Current page number
        page_size: Items per page
        code: ResponseCode object
        message: Optional custom message
    
    Returns:
        Standardized paginated response
    """
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "success": True,
        "code": code.code,
        "message": message or code.message,
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
