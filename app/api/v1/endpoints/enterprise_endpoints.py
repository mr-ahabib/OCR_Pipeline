"""Enterprise OCR endpoints — admin and super-user access."""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.middleware.auth import require_admin, require_super_user
from app.models.user import User, UserRole
from app.schemas.enterprise_schemas import (
    EnterpriseCreate,
    EnterpriseListResponse,
    EnterpriseOCRHistoryResponse,
    EnterprisePaymentStatusUpdate,
    EnterpriseResponse,
    EnterpriseUpdate,
    EnterpriseBillingSummary,
)
from app.services.enterprise_service import (
    create_enterprise,
    get_enterprise,
    get_enterprise_ocr_history,
    get_billing_summary,
    list_enterprises,
    save_enterprise_ocr_document,
    soft_delete_enterprise,
    update_enterprise,
    update_payment_status,
    _get_enterprise_orm,
)
from app.schemas.enterprise_schemas import EnterpriseOCRDocumentCreate
from app.services.ocr_service import process_file, process_file_auto, detect_file_type, select_ocr_engine
from app.utils.file_storage import save_uploaded_file
from app.utils.enterprise_invoice import generate_enterprise_invoice_pdf
from app.utils.pdf_utils import count_pdf_pages
from app.errors.exceptions import NotFoundException, ForbiddenException
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _is_super(user: User) -> bool:
    return user.role == UserRole.SUPER_USER


@router.post("/", response_model=EnterpriseResponse, status_code=201)
async def create_enterprise_endpoint(
    payload:      EnterpriseCreate,
    current_user: User = Depends(require_admin),
    db:           Session = Depends(get_db),
):
    """
    ## Create a new enterprise contract

    **Role:** ADMIN or SUPER_USER.

    **Auth:** `Authorization: Bearer <token>` header required.

    Creates an enterprise record with quota, billing, and contact details.
    `total_cost` is auto-calculated as `total_pages × unit_price`.
    `due_amount` is auto-calculated as `total_cost − advance_bill`.
    `duration_days` is auto-calculated from `start_date` and `end_date`.

    ### Required fields (JSON body)
    | Field           | Type   | Description                                  |
    |-----------------|--------|----------------------------------------------|
    | name            | string | Enterprise / client name                     |
    | total_pages     | int    | Pages quota to allocate                      |
    | unit_price      | float  | Price per page in BDT (default 10.0)         |
    | advance_bill    | float  | Amount paid in advance (default 0)           |

    ### Optional fields
    `phone`, `email`, `description`, `start_date`, `end_date`,
    `no_of_documents`, `payment_status`

    ### Response — EnterpriseResponse
    Full contract record including computed `total_cost`, `due_amount`,
    `duration_days`, `pages_remaining`, and `created_by_name`.
    """
    return create_enterprise(db, payload, created_by=current_user.id)


@router.get("/", response_model=EnterpriseListResponse)
async def list_enterprises_endpoint(
    skip:         int          = Query(0,   ge=0),
    limit:        int          = Query(100, ge=1, le=500),
    current_user: User         = Depends(require_admin),
    db:           Session      = Depends(get_db),
):
    """
    ## List enterprise contracts

    **Role:** ADMIN or SUPER_USER.

    - **ADMIN** sees only their own enterprises.
    - **SUPER_USER** sees all enterprises across all admins, including
      `created_by_name` so you know who created each one.

    ### Query parameters
    | Param | Default | Description       |
    |-------|---------|-------------------|
    | skip  | 0       | Pagination offset |
    | limit | 100     | Max records (≤500)|

    ### Frontend integration
    - Render in an "Enterprise Management" table.
    - SUPER_USER: add a "Created By" column from `created_by_name`.
    """
    is_super = _is_super(current_user)
    created_by_filter = None if is_super else current_user.id
    total, enterprises = list_enterprises(
        db, created_by=created_by_filter, skip=skip, limit=limit
    )
    return EnterpriseListResponse(total=total, enterprises=enterprises)


@router.get("/admin/billing-summary", response_model=EnterpriseBillingSummary)
async def billing_summary_endpoint(
    current_user: User    = Depends(require_super_user),
    db:           Session = Depends(get_db),
):
    """
    ## Platform-wide billing summary

    **Role:** SUPER_USER only.

    Returns aggregrated billing figures across **all** active enterprises:
    total contract value, total advance billed, total due amount, and
    counts per payment status (`paid`, `partial_paid`, `due`).

    ### Frontend integration
    - Display as a summary dashboard widget for the super-user admin panel.
    - Useful for reporting and collections follow-up.
    """
    return get_billing_summary(db)


@router.get("/admin/all", response_model=EnterpriseListResponse)
async def admin_list_all_enterprises(
    skip:         int     = Query(0,   ge=0),
    limit:        int     = Query(100, ge=1, le=500),
    current_user: User    = Depends(require_super_user),
    db:           Session = Depends(get_db),
):
    """
    ## List ALL enterprise contracts (super-user view)

    **Role:** SUPER_USER only.

    Returns every enterprise on the platform regardless of creator.
    Each record includes `created_by_name` (the admin who created it)
    so you can see *who is managing which client*.

    ### Response
    Same as `GET /enterprise/` but unscoped to any creator.
    """
    total, enterprises = list_enterprises(db, created_by=None, skip=skip, limit=limit)
    return EnterpriseListResponse(total=total, enterprises=enterprises)


@router.get("/{enterprise_id}", response_model=EnterpriseResponse)
async def get_enterprise_endpoint(
    enterprise_id: int,
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Get a single enterprise contract

    **Role:** ADMIN or SUPER_USER.

    - **ADMIN:** can only fetch their own enterprises.
    - **SUPER_USER:** can fetch any enterprise.

    ### Response — EnterpriseResponse
    Full contract details including billing, quota, and creator info.

    ### Error codes
    - HTTP 404 → not found or not owned by the caller.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    ent = get_enterprise(db, enterprise_id, created_by=owner_filter,
                         include_deleted=is_super)
    if not ent:
        raise NotFoundException(detail="Enterprise not found")
    return ent


@router.put("/{enterprise_id}", response_model=EnterpriseResponse)
async def update_enterprise_endpoint(
    enterprise_id: int,
    payload:       EnterpriseUpdate,
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Update an enterprise contract

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    All fields are optional — only supplied fields are updated.
    `total_cost`, `due_amount`, and `duration_days` are recomputed
    automatically after any change.

    ### Editable fields
    `name`, `phone`, `email`, `description`, `total_pages`, `unit_price`,
    `start_date`, `end_date`, `advance_bill`, `no_of_documents`, `payment_status`

    ### Error codes
    - HTTP 404 → not found or access denied.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    updated = update_enterprise(db, enterprise_id, payload, created_by=owner_filter)
    if not updated:
        raise NotFoundException(detail="Enterprise not found or access denied")
    return updated


@router.patch("/{enterprise_id}/payment-status", response_model=EnterpriseResponse)
async def update_payment_status_endpoint(
    enterprise_id: int,
    payload:       EnterprisePaymentStatusUpdate,
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Update payment status (and optionally advance bill)

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    Marks the enterprise as `paid`, `partial_paid`, or `due`.
    Optionally update the `advance_bill` amount at the same time —
    `due_amount` is recalculated automatically.

    ### Required fields (JSON body)
    | Field          | Type   | Description                            |
    |----------------|--------|----------------------------------------|
    | payment_status | string | `paid` / `partial_paid` / `due`        |
    | advance_bill   | float  | (optional) New advance amount in BDT   |

    ### Frontend integration
    - Render as a dropdown / action button in the enterprise detail page.
    - Show the updated `due_amount` immediately after response.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    updated = update_payment_status(db, enterprise_id, payload, created_by=owner_filter)
    if not updated:
        raise NotFoundException(detail="Enterprise not found or access denied")
    return updated


@router.delete("/{enterprise_id}", status_code=200)
async def delete_enterprise_endpoint(
    enterprise_id: int,
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Soft-delete an enterprise contract

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    Marks the enterprise as deleted; it will no longer appear in list/get
    queries for admins. Super-users can still see it with `include_deleted`.
    OCR history is preserved for auditing.

    ### Error codes
    - HTTP 404 → not found or access denied.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    ok = soft_delete_enterprise(db, enterprise_id, created_by=owner_filter)
    if not ok:
        raise NotFoundException(detail="Enterprise not found or access denied")
    return {"message": "Enterprise deleted successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# Invoice download
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{enterprise_id}/invoice")
async def download_invoice(
    enterprise_id: int,
    tz: str            = Query("UTC", description="IANA timezone for invoice display, e.g. Asia/Dhaka, America/New_York"),
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Download enterprise invoice as PDF

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    Generates a professional PDF invoice on the fly and returns it as a
    file download. The invoice includes:
    - Enterprise name, contact, and description
    - Contract period and duration
    - Pages allocated, used, and remaining
    - Total cost, advance billed, and due amount
    - Payment status badge (green/orange/red)
    - Terms & conditions (no online payment for enterprise contracts)

    ### Response
    `application/pdf` binary — set `<a download>` on the frontend.

    ### Frontend integration
    ```js
    const res = await axios.get(`/api/v1/enterprise/${id}/invoice`,
      { headers: { Authorization: `Bearer ${token}` }, responseType: 'blob' });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement('a');
    a.href = url; a.download = `invoice-${id}.pdf`; a.click();
    ```
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    ent_orm = _get_enterprise_orm(db, enterprise_id, created_by=owner_filter,
                                  include_deleted=is_super)
    if not ent_orm:
        raise NotFoundException(detail="Enterprise not found or access denied")

    from app.models.user import User as UserModel
    creator = db.query(UserModel).filter(UserModel.id == ent_orm.created_by).first()
    creator_name = (creator.full_name or creator.username) if creator else ""

    pdf_bytes = generate_enterprise_invoice_pdf(
        enterprise=ent_orm,
        creator_name=creator_name,
        display_timezone=tz,
    )
    filename = f"enterprise-invoice-{ent_orm.id}-{ent_orm.name.replace(' ', '_')}.pdf"
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Enterprise OCR
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{enterprise_id}/ocr", status_code=200)
async def enterprise_ocr(
    enterprise_id: int,
    file:  UploadFile = File(...),
    current_user: User    = Depends(require_admin),
    db:           Session = Depends(get_db),
):
    """
    ## Run OCR under an enterprise contract

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    Processes the uploaded document against the enterprise's page quota.
    The result is saved to `enterprise_ocr_documents` and the enterprise's
    `pages_used` counter is incremented automatically.

    ### Required form fields (multipart/form-data)
    | Field | Type   | Default | Description                                       |
    |-------|--------|---------|---------------------------------------------------|
    | file  | file   | —       | Document (PDF / JPEG / PNG / TIFF, max 50 MB)     |

    ### Quota enforcement
    - If `pages_used + pages_in_file > total_pages` → **HTTP 402** (quota exceeded).
    - `pages_remaining` in `GET /{enterprise_id}` shows the live balance.

    ### Response
    ```json
    {
      "pages_info": [...],
      "summary": { ... },
      "quota": { "pages_used": 5, "total_pages": 100, "pages_remaining": 95 },
      "document_id": 42
    }
    ```

    ### Frontend integration
    ```js
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    const { data } = await axios.post(
      `/api/v1/enterprise/${enterpriseId}/ocr`, form,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    ```
    - HTTP 402 → page quota exhausted; show "Contact admin to top up".
    - HTTP 404 → enterprise not found / access denied.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    ent_orm = _get_enterprise_orm(db, enterprise_id, created_by=owner_filter)
    if not ent_orm:
        raise NotFoundException(detail="Enterprise not found or access denied")

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    file_type = detect_file_type(content)
    if file_type == "unknown":
        raise HTTPException(
            status_code=415,
            detail="Unsupported file format. Use PDF, JPEG, PNG, BMP, WebP, or TIFF.",
        )

    if file_type == "pdf":
        try:
            pages_in_file = count_pdf_pages(content)
        except Exception:
            pages_in_file = 1
    else:
        pages_in_file = 1

    pages_remaining = max(0, ent_orm.total_pages - (ent_orm.pages_used or 0))
    if pages_in_file > pages_remaining:
        raise HTTPException(
            status_code=402,
            detail={
                "message": (
                    f"Page quota exceeded. This file has {pages_in_file} page(s) but "
                    f"only {pages_remaining} page(s) remain for enterprise '{ent_orm.name}'."
                ),
                "pages_in_file":  pages_in_file,
                "pages_remaining": pages_remaining,
                "total_pages":    ent_orm.total_pages,
            },
        )

    request_start = time.time()
    result = await process_file_auto(
        content,
        user=current_user,
        user_id=current_user.id,
        user_email=current_user.email,
    )
    duration = time.time() - request_start

    # Persist file and save DB record
    try:
        file_path = save_uploaded_file(content, file.filename)
    except Exception:
        file_path = None

    doc_payload = EnterpriseOCRDocumentCreate(
        enterprise_id   = enterprise_id,
        processed_by    = current_user.id,
        filename        = file.filename,
        file_path       = file_path,
        file_type       = file_type,
        file_size       = len(content),
        ocr_mode        = result["mode"],
        ocr_engine      = result["engine"],
        languages       = result["languages"],
        extracted_text  = result["text"],
        confidence      = result["confidence"],
        total_pages     = result["pages"],
        pages_data      = result.get("pages_data"),
        processing_time = duration,
        character_count = len(result["text"]),
    )
    saved_doc = save_enterprise_ocr_document(db, doc_payload)

    # Build page-by-page response
    pages_data = result.get("pages_data") or []
    if pages_data and len(pages_data) > 1:
        pages_info = [
            {
                "page_number":    p["page_number"],
                "confidence":     round(p["confidence"], 2),
                "character_count": p["character_count"],
                "text":           p["text"],
            }
            for p in pages_data
        ]
    else:
        pages_info = [{
            "page_number":    1,
            "confidence":     round(result["confidence"], 2),
            "character_count": len(result["text"]),
            "text":           result["text"],
        }]

    # Refresh ORM to get updated pages_used
    db.refresh(ent_orm)
    new_pages_used = ent_orm.pages_used or 0

    return {
        "pages_info": pages_info,
        "summary": {
            "total_pages":        result["pages"],
            "average_confidence": round(result["confidence"], 2),
            "total_characters":   len(result["text"]),
            "processing_details": (
                f"{result['pages']} page(s) processed with "
                f"{result['confidence']:.2f}% confidence in {duration:.2f}s"
            ),
        },
        "quota": {
            "pages_used":      new_pages_used,
            "total_pages":     ent_orm.total_pages,
            "pages_remaining": max(0, ent_orm.total_pages - new_pages_used),
        },
        "document_id": saved_doc.id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# OCR History
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{enterprise_id}/ocr-history", response_model=EnterpriseOCRHistoryResponse)
async def enterprise_ocr_history(
    enterprise_id: int,
    skip:          int     = Query(0,   ge=0),
    limit:         int     = Query(100, ge=1, le=500),
    current_user:  User    = Depends(require_admin),
    db:            Session = Depends(get_db),
):
    """
    ## Get OCR processing history for an enterprise

    **Role:** ADMIN (own enterprises) or SUPER_USER (any enterprise).

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns every OCR document processed under the given enterprise contract,
    newest first. Each record includes who processed it (`processor_name`).

    ### Path parameter
    | Param         | Description             |
    |---------------|-------------------------|
    | enterprise_id | Enterprise contract ID  |

    ### Query parameters
    | Param | Default | Description       |
    |-------|---------|-------------------|
    | skip  | 0       | Pagination offset |
    | limit | 100     | Max results (≤500)|

    ### Frontend integration
    - Show in a "Document History" tab inside the enterprise detail page.
    - SUPER_USER: include "Processed By" column from `processor_name`.
    """
    is_super = _is_super(current_user)
    owner_filter = None if is_super else current_user.id
    total, docs = get_enterprise_ocr_history(
        db, enterprise_id, skip=skip, limit=limit, created_by=owner_filter
    )
    return EnterpriseOCRHistoryResponse(total=total, documents=docs)


@router.get("/admin/ocr-history/all", response_model=EnterpriseOCRHistoryResponse)
async def all_enterprise_ocr_history(
    skip:         int     = Query(0,   ge=0),
    limit:        int     = Query(100, ge=1, le=500),
    current_user: User    = Depends(require_super_user),
    db:           Session = Depends(get_db),
):
    """
    ## All-enterprise OCR history (super-user view)

    **Role:** SUPER_USER only.

    Returns OCR processing records across **all** enterprise contracts on the
    platform, newest first. Each record shows `enterprise_id`, `processed_by`,
    and `processor_name` so you can audit who processed what, and under which
    client's contract.

    ### Query parameters
    | Param | Default | Description       |
    |-------|---------|-------------------|
    | skip  | 0       | Pagination offset |
    | limit | 100     | Max results (≤500)|

    ### Frontend integration
    - Render in a global "Enterprise OCR Activity" log in the super-user dashboard.
    - Group or filter by `enterprise_id` or `processed_by` on the frontend.
    """
    from app.models.enterprise import EnterpriseOCRDocument as EOD
    from app.services.enterprise_service import _enrich_ocr_doc

    q     = db.query(EOD).order_by(EOD.created_at.desc())
    total = q.count()
    docs  = q.offset(skip).limit(limit).all()
    return EnterpriseOCRHistoryResponse(
        total=total,
        documents=[_enrich_ocr_doc(db, d) for d in docs],
    )
