"""Custom exceptions for error handling"""
from fastapi import HTTPException, status


class BaseHTTPException(HTTPException):
    """Base exception class for all custom HTTP exceptions"""
    def __init__(self, detail: str = None, headers: dict = None):
        super().__init__(
            status_code=self.status_code,
            detail=detail or self.detail,
            headers=headers
        )


class BadRequestException(BaseHTTPException):
    """400 Bad Request"""
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Bad request"


class UnauthorizedException(BaseHTTPException):
    """401 Unauthorized"""
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Not authenticated"
    
    def __init__(self, detail: str = None):
        super().__init__(
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class ForbiddenException(BaseHTTPException):
    """403 Forbidden"""
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Forbidden: Insufficient permissions"


class NotFoundException(BaseHTTPException):
    """404 Not Found"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class ConflictException(BaseHTTPException):
    """409 Conflict"""
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource already exists"


class UnprocessableEntityException(BaseHTTPException):
    """422 Unprocessable Entity"""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "Unprocessable entity"


class InternalServerException(BaseHTTPException):
    """500 Internal Server Error"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = "Internal server error"


class ServiceUnavailableException(BaseHTTPException):
    """503 Service Unavailable"""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "Service temporarily unavailable"


class ValidationException(BaseHTTPException):
    """422 Validation Error"""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "Validation error"


class DatabaseException(InternalServerException):
    """Database operation failed"""
    detail = "Database operation failed"


class FileUploadException(BadRequestException):
    """File upload failed"""
    detail = "File upload failed"


class OCRProcessingException(InternalServerException):
    """OCR processing failed"""
    detail = "OCR processing failed"
