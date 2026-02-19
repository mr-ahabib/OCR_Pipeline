# OCR Pipeline - Production-Ready Bangla Text Extraction

High-accuracy OCR system optimized for Bangla (Bengali) text extraction with multi-engine support, JWT authentication, and production-grade architecture.

## 🌟 Features

- **Multi-Engine OCR**: Tesseract + EasyOCR + Google DocAI
- **Bangla Optimized**: Specialized configuration for Bengali script
- **Multiple Modes**: Bangla-only, English-only, and Mixed mode
- **High Accuracy**: Best trained data and multiple extraction strategies
- **Layout Preservation**: Maintains original document structure
- **JWT Authentication**: Secure role-based access control
- **🆕 Automatic Free Trial**: 3 free OCR requests per browser (zero config!)
- **Browser Fingerprinting**: Automatic device/browser tracking
- **Secure Cookie Tracking**: Persistent trial counting across sessions
- **Production-Ready**: Error handling, validation, database migrations

## 📁 Project Structure

```
OCR_Pipeline/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── api.py                    # API router aggregation
│   │       └── endpoints/
│   │           ├── auth_endpoints.py     # Authentication endpoints
│   │           ├── ocr_endpoints.py      # OCR processing endpoints
│   │           └── document_endpoints.py # Document management
│   ├── core/
│   │   ├── config.py                     # Configuration settings
│   │   ├── dependencies.py               # Dependency injection
│   │   └── response_codes.py             # HTTP response codes
│   ├── db/
│   │   ├── base.py                       # Database base class
│   │   ├── session.py                    # Database session
│   │   └── init_db.py                    # Database initialization
│   ├── errors/
│   │   ├── exceptions.py                 # Custom exceptions
│   │   └── handlers.py                   # Exception handlers
│   ├── middleware/
│   │   └── auth.py                       # Authentication middleware
│   ├── models/
│   │   ├── ocr_document.py               # OCR document model
│   │   └── user.py                       # User model
│   ├── schemas/
│   │   ├── auth_schemas.py               # Auth request/response schemas (Pydantic validation)
│   │   └── ocr_schemas.py                # OCR request/response schemas (Pydantic validation)
│   ├── services/
│   │   ├── auth_service.py               # Authentication logic
│   │   ├── ocr_service.py                # OCR processing logic
│   │   └── ocr_crud.py                   # Database CRUD operations
│   ├── ocr/
│   │   ├── tesseract_engine.py           # Tesseract OCR engine
│   │   ├── easyocr_engine.py             # EasyOCR engine
│   │   └── google_docai_engine.py        # Google DocAI engine
│   ├── utils/
│   │   ├── logger.py                     # Logging configuration
│   │   ├── pdf_utils.py                  # PDF processing utilities
│   │   └── confidence.py                 # Confidence calculation
│   └── main.py                           # FastAPI application entry
├── alembic/                              # Database migrations
├── .env                                  # Environment variables
├── Makefile                              # Development commands
├── requirements.txt                      # Python dependencies
└── README.md                             # This file
```

## 🚀 Quick Start

### 1. System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils postgresql
```

**macOS:**
```bash
brew install tesseract poppler postgresql
```

### 2. Install Python Dependencies

```bash
make install
# or
pip install -r requirements.txt
```

### 3. Configure Environment

Copy and configure the environment file:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Database
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ocr_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password

# JWT Authentication
SECRET_KEY=your-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OCR Settings
DEFAULT_OCR_LANG=ben
OCR_CONFIDENCE_THRESHOLD=0.6
```

### 4. Setup Database

```bash
# Initialize database and create tables
make db-init

# Run migrations
make migrate-up
```

### 5. Run Application

```bash
# Development mode
make run

# Production mode
make run-prod
```

The API will be available at: `http://localhost:8000`  
API Documentation: `http://localhost:8000/docs`

## 🔐 Authentication

### User Roles

The system supports 4 user roles with hierarchical permissions:

- **SUPER_USER**: Full system access
- **ADMIN**: User management and all operations
- **ENTERPRISE**: Standard operations
- **USER**: Basic operations

### Default Admin Account

After running `make db-init`, a default admin account is created:

- **Username**: `admin`
- **Password**: `Admin@123`

⚠️ **IMPORTANT**: Change the default password immediately after first login!

### Authentication Flow

1. **Register** a new user:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "user@example.com",
    "password": "SecurePass123",
    "full_name": "New User"
  }'
```

2. **Login** to get access token:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@ocrpipeline.com&password=Qanun@Admin@123"
```

**Note**: The field is called `username` for OAuth2 compatibility, but you should enter your **email address**.

3. **Use token** in subsequent requests:
```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 📝 API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/v1/auth/register` | Register new user | No |
| POST | `/api/v1/auth/login` | Login with email (OAuth2) | No |
| GET | `/api/v1/auth/me` | Get current user | Yes |
| POST | `/api/v1/auth/change-password` | Change password | Yes |
| GET | `/api/v1/auth/users` | List all users | Admin |
| DELETE | `/api/v1/auth/users/{id}` | Delete user | Super Admin |
| PATCH | `/api/v1/auth/users/{id}/toggle-active` | Toggle user active | Admin |
| PATCH | `/api/v1/auth/users/{id}/role` | Update user role | Super Admin |

### OCR Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/v1/ocr/pages` | Extract page by page text | Yes |
| POST | `/api/v1/ocr/free-trial` | 🆕 Free trial OCR (3 uses/browser) | No |
| GET | `/api/v1/ocr/trial-status` | 🆕 Check free trial status | No |

> **Note**: Free trial endpoints automatically track usage via browser fingerprinting and cookies - no configuration needed!
> See [FREE_TRIAL_SYSTEM.md](FREE_TRIAL_SYSTEM.md) for details.

### Document Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/v1/documents/` | List all documents | Yes |
| GET | `/api/v1/documents/{id}` | Get document by ID | Yes |
| DELETE | `/api/v1/documents/{id}` | Delete document | Yes |
| GET | `/api/v1/documents/count` | Get document count | Yes |

## 🛠️ Development Commands (Makefile)

### Installation & Setup
```bash
make install          # Install all dependencies
make dev              # Install dev dependencies
```

### Running Application
```bash
make run              # Start development server
make run-prod         # Start production server
```

### Database Management
```bash
make migrate-up       # Apply all pending migrations
make migrate-down     # Rollback last migration
make migrate-create MSG='message'  # Create new migration
make migrate-current  # Show current migration version
make migrate-history  # Show migration history
make db-init          # Initialize database tables
```

### Testing & Quality
```bash
make test             # Run all tests
make lint             # Run code linting
make format           # Format code with black
```

### Cleanup
```bash
make clean            # Remove cache files
make clean-all        # Remove cache and virtual environment
```

## 📊 Response Codes System

The project uses a standardized response code system for consistent API responses.

### Success Codes (2xx)

```python
from app.core.response_codes import SuccessCode, success_response

return success_response(
    code=SuccessCode.CREATED,
    data={"id": 123, "name": "Document"},
    message="Document created successfully"
)
```

**Available Success Codes:**
- `SuccessCode.OK` - Request processed successfully (200)
- `SuccessCode.RETRIEVED` - Data retrieved successfully (200)
- `SuccessCode.UPDATED` - Resource updated successfully (200)
- `SuccessCode.DELETED` - Resource deleted successfully (200)
- `SuccessCode.CREATED` - Resource created successfully (201)
- `SuccessCode.USER_REGISTERED` - User registered successfully (201)

### Error Codes (4xx, 5xx)

```python
from app.core.response_codes import ErrorCode, error_response

return error_response(
    code=ErrorCode.INVALID_CREDENTIALS,
    message="Invalid username or password"
)
```

**Available Error Codes:**
- `ErrorCode.BAD_REQUEST` - Bad request (400)
- `ErrorCode.INVALID_INPUT` - Invalid input provided (400)
- `ErrorCode.INVALID_FILE_TYPE` - Invalid file type (400)
- `ErrorCode.FILE_TOO_LARGE` - File size exceeds limit (400)
- `ErrorCode.UNAUTHORIZED` - Authentication required (401)
- `ErrorCode.INVALID_CREDENTIALS` - Invalid credentials (401)
- `ErrorCode.TOKEN_EXPIRED` - Token has expired (401)
- `ErrorCode.FORBIDDEN` - Access forbidden (403)
- `ErrorCode.INSUFFICIENT_PERMISSIONS` - Insufficient permissions (403)
- `ErrorCode.NOT_FOUND` - Resource not found (404)
- `ErrorCode.USER_NOT_FOUND` - User not found (404)
- `ErrorCode.CONFLICT` - Resource conflict (409)
- `ErrorCode.USERNAME_EXISTS` - Username already exists (409)
- `ErrorCode.VALIDATION_ERROR` - Validation error (422)
- `ErrorCode.INTERNAL_ERROR` - Internal server error (500)
- `ErrorCode.DATABASE_ERROR` - Database operation failed (500)
- `ErrorCode.OCR_PROCESSING_ERROR` - OCR processing failed (500)

### Paginated Response

```python
from app.core.response_codes import paginated_response

return paginated_response(
    data=items,
    total=100,
    page=1,
    page_size=10
)
```

## ✅ Validation System

The project uses **Pydantic v2** for all validation through schema models. All validation logic is defined declaratively in schema classes using Pydantic validators and constraints.

### Schema Validation Example

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must contain only alphanumeric characters and underscores')
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v
```

**Benefits:**
- Automatic validation on FastAPI endpoints
- Type safety and IDE autocomplete
- JSON Schema generation for API documentation
- No manual validation functions needed

## 🗄️ Database Migrations

This project uses Alembic for database migrations.

### Create Migration

```bash
# Create new migration with message
make migrate-create MSG='add new column to users'

# Or use alembic directly
alembic revision --autogenerate -m "add new column"
```

### Apply Migrations

```bash
# Upgrade to latest version
make migrate-up

# Upgrade to specific version
alembic upgrade <revision>
```

### Rollback Migrations

```bash
# Rollback last migration
make migrate-down

# Rollback to specific version
alembic downgrade <revision>
```

### Migration History

```bash
# Show all migrations
make migrate-history

# Show current version
make migrate-current
```

## 🔧 Configuration

### Environment Variables

All configuration is managed through environment variables in the `.env` file:

```env
# Database Configuration
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ocr_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password

# JWT Authentication
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OCR Settings
DEFAULT_OCR_LANG=ben
OCR_CONFIDENCE_THRESHOLD=0.6
MAX_UPLOAD_SIZE_MB=50

# Logging
LOG_LEVEL=INFO
LOG_FILE=app/logs/logs.txt
```

## 🧪 Testing

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest --cov=app --cov-report=html
```

## 📋 Error Handling

The project includes comprehensive error handling:

### Custom Exceptions

```python
from app.errors.exceptions import (
    ValidationException,
    UnauthorizedException,
    NotFoundException
)

# Raise custom exception
raise ValidationException(detail="Invalid input data")
```

### Global Exception Handlers

All exceptions are caught and formatted consistently by global handlers in `app/errors/handlers.py`.

## 🔒 Security Best Practices

1. **Change default admin password** immediately after setup
2. **Use strong SECRET_KEY** in production (generate with `openssl rand -hex 32`)
3. **Enable HTTPS** in production
4. **Use environment variables** for sensitive data
5. **Regular security updates** for dependencies
6. **Database backups** regularly
7. **Rate limiting** on authentication endpoints
8. **Input validation** on all endpoints

## 📈 Performance

- **60-70% faster processing** with optimized OCR strategies
- **Smart engine selection** based on file type
- **Early exit strategy** for high-confidence results
- **Parallel processing** support
- **Caching** for repeated operations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License.

## 🐛 Troubleshooting

**⚠️ Important:** For detailed troubleshooting guides, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Common Issues Quick Reference

#### Database Connection Issues

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql
sudo systemctl start postgresql

# Test connection
PGPASSWORD=your_password psql -U postgres -h localhost -l
```

#### Migration Issues

**Error: "type 'userrole' already exists"**

This happens when tables were created with `init_db()` but migrations weren't tracked:

```bash
# Fix: Mark current state as migrated
make migrate-stamp

# Verify
make migrate-current
```

**For other migration issues:**
```bash
# View current state
make migrate-current
make migrate-history

# Reset migrations (DANGER: destroys data)
make db-recreate
```

#### OCR Engine Issues

```bash
# Verify Tesseract installation
tesseract --version

# Check language data (should show 'ben' for Bangla)
tesseract --list-langs

# Install Bangla language data if missing
sudo apt-get install tesseract-ocr-ben
```

#### Authentication Issues

```bash
# Reset super admin password by updating .env
SUPER_ADMIN_PASSWORD=YourNewPassword123!

# Then recreate database
make db-recreate
```

**📖 See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for complete troubleshooting guide.**

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Check existing documentation
- Review API docs at `http://localhost:8000/docs`

---

**Made with ❤️ for accurate Bangla text extraction**
