"""Error handling module"""
from app.errors.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    UnprocessableEntityException,
    InternalServerException,
    ServiceUnavailableException,
    ValidationException,
    DatabaseException,
    FileUploadException,
    OCRProcessingException
)
from app.errors.response_codes import (
    SuccessCode,
    ErrorCode,
    success_response,
    error_response,
    paginated_response
)

__all__ = [
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "UnprocessableEntityException",
    "InternalServerException",
    "ServiceUnavailableException",
    "ValidationException",
    "DatabaseException",
    "FileUploadException",
    "OCRProcessingException",
    "SuccessCode",
    "ErrorCode",
    "success_response",
    "error_response",
    "paginated_response"
]
