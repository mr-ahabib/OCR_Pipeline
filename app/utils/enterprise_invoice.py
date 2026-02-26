"""Enterprise invoice PDF generator - uses fpdf2 (already in requirements.txt)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fpdf import FPDF

from app.models.enterprise import Enterprise, EnterprisePaymentStatus


def _resolve_tz(tz_name: str) -> ZoneInfo:
    """Return a ZoneInfo for *tz_name*, falling back to UTC on invalid names."""
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("UTC")


# Status colour palette
_STATUS_COLORS = {
    EnterprisePaymentStatus.PAID:         (22, 163, 74),    # green
    EnterprisePaymentStatus.PARTIAL_PAID: (234, 88,  12),   # orange
    EnterprisePaymentStatus.DUE:          (220, 38,  38),   # red
}
_STATUS_LABELS = {
    EnterprisePaymentStatus.PAID:         "PAID",
    EnterprisePaymentStatus.PARTIAL_PAID: "PARTIAL PAID",
    EnterprisePaymentStatus.DUE:          "DUE",
}


def generate_enterprise_invoice_pdf(
    enterprise: Enterprise,
    creator_name: str = "",
    invoice_number: Optional[str] = None,
    generated_at: Optional[datetime] = None,
    display_timezone: str = "UTC",
) -> bytes:
    """
    Generate a professional enterprise invoice PDF.
    Returns raw PDF bytes suitable for a download endpoint.
    """
    tz = _resolve_tz(display_timezone)
    now       = (generated_at or datetime.now(timezone.utc)).astimezone(tz)
    inv_no    = invoice_number or f"ENT-{enterprise.id:06d}"
    date_str  = now.strftime("%B %d, %Y")
    time_str  = now.strftime("%I:%M %p %Z")

    status_color = _STATUS_COLORS.get(enterprise.payment_status, (75, 85, 99))
    status_label = _STATUS_LABELS.get(enterprise.payment_status, str(enterprise.payment_status))

    pages_remaining = max(0, enterprise.total_pages - (enterprise.pages_used or 0))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    pdf.set_fill_color(15, 23, 42)           # dark navy
    pdf.rect(0, 0, 210, 38, "F")

    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(14, 9)
    pdf.cell(120, 12, "DoceanAI", ln=0)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(148, 163, 184)
    pdf.set_xy(14, 23)
    pdf.cell(120, 8, "Enterprise OCR Platform", ln=0)

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(140, 9)
    pdf.cell(56, 10, "INVOICE", align="R", ln=0)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.set_xy(140, 23)
    pdf.cell(56, 8, f"#{inv_no}", align="R", ln=1)

    pdf.set_y(46)
    pdf.set_text_color(55, 65, 81)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_x(14);  pdf.cell(85, 5, "BILLED TO", ln=0)
    pdf.set_x(110); pdf.cell(86, 5, "INVOICE DETAILS", ln=1)

    # Client name
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(17, 24, 39)
    pdf.set_x(14);  pdf.cell(85, 7, enterprise.name, ln=0)
    # Invoice No
    pdf.set_x(110); pdf.set_font("Helvetica", "", 9); pdf.set_text_color(75, 85, 99)
    pdf.cell(40, 7, "Invoice No:", ln=0)
    pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(17, 24, 39)
    pdf.cell(46, 7, inv_no, ln=1)

    # Client email
    pdf.set_font("Helvetica", "", 9); pdf.set_text_color(75, 85, 99)
    pdf.set_x(14);  pdf.cell(85, 6, enterprise.email or "-", ln=0)
    # Date
    pdf.set_x(110); pdf.cell(40, 6, "Date Issued:", ln=0)
    pdf.set_text_color(17, 24, 39); pdf.cell(46, 6, date_str, ln=1)

    # Client phone
    pdf.set_x(14);  pdf.set_text_color(75, 85, 99); pdf.cell(85, 6, enterprise.phone or "-", ln=0)
    # Time
    pdf.set_x(110); pdf.cell(40, 6, "Time:", ln=0)
    pdf.set_text_color(17, 24, 39); pdf.cell(46, 6, time_str, ln=1)

    # Contract period
    start_s = enterprise.start_date.strftime("%d %b %Y") if enterprise.start_date else "-"
    end_s   = enterprise.end_date.strftime("%d %b %Y")   if enterprise.end_date   else "-"
    pdf.set_x(14); pdf.set_text_color(75, 85, 99)
    pdf.cell(85, 6, f"Period: {start_s} to {end_s}", ln=0)
    # Created by
    pdf.set_x(110); pdf.cell(40, 6, "Account Manager:", ln=0)
    pdf.set_text_color(17, 24, 39); pdf.cell(46, 6, creator_name or "-", ln=1)

    # Status badge row
    pdf.set_x(110); pdf.set_text_color(75, 85, 99); pdf.set_font("Helvetica", "", 9)
    pdf.cell(40, 6, "Payment Status:", ln=0)
    pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*status_color)
    pdf.cell(46, 6, status_label, ln=1)

    pdf.ln(2)

    pdf.set_draw_color(226, 232, 240)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(3)

    if enterprise.description:
        desc = enterprise.description[:180] + "..." if len(enterprise.description) > 180 else enterprise.description
        pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(55, 65, 81)
        pdf.set_x(14); pdf.cell(182, 5, "PROJECT DESCRIPTION", ln=1)
        pdf.set_font("Helvetica", "I", 8.5); pdf.set_text_color(75, 85, 99)
        pdf.set_x(14)
        pdf.multi_cell(182, 4.5, desc)
        pdf.ln(2)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)

    col_w  = [80, 26, 30, 30, 30]
    heads  = ["Description", "Qty (Pages)", "Unit Price", "Amount", ""]
    aligns = ["L", "C", "R", "R", "R"]

    pdf.set_fill_color(15, 23, 42); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_x(14)
    for i, h in enumerate(heads):
        pdf.cell(col_w[i], 8, h, fill=True, align=aligns[i])
    pdf.ln()

    # Row: OCR service
    pdf.set_fill_color(241, 245, 249); pdf.set_text_color(17, 24, 39)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(14)
    pdf.cell(col_w[0], 8, "Enterprise OCR Service (Allocated)", fill=True, align="L")
    pdf.cell(col_w[1], 8, str(enterprise.total_pages),                       fill=True, align="C")
    pdf.cell(col_w[2], 8, f"BDT {enterprise.unit_price:.2f}",               fill=True, align="R")
    pdf.cell(col_w[3], 8, f"BDT {enterprise.total_cost:.2f}",               fill=True, align="R")
    pdf.cell(col_w[4], 8, "",                                                fill=True)
    pdf.ln()

    # Row: pages used (informational)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_x(14)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w[0], 7, "  >> Pages Used (as of invoice date)", fill=False, align="L")
    pdf.cell(col_w[1], 7, str(enterprise.pages_used or 0),        fill=False, align="C")
    pdf.cell(col_w[2], 7, "-",                                    fill=False, align="R")
    pdf.cell(col_w[3], 7, "-",                                    fill=False, align="R")
    pdf.cell(col_w[4], 7, "",                                     fill=False)
    pdf.ln()

    pdf.set_x(14)
    pdf.cell(col_w[0], 7, "  >> Pages Remaining",                 fill=False, align="L")
    pdf.cell(col_w[1], 7, str(pages_remaining),                  fill=False, align="C")
    pdf.cell(col_w[2], 7, "-",                                   fill=False, align="R")
    pdf.cell(col_w[3], 7, "-",                                   fill=False, align="R")
    pdf.cell(col_w[4], 7, "",                                    fill=False)
    pdf.ln()

    # Row: number of documents
    if enterprise.no_of_documents:
        pdf.set_x(14)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(col_w[0], 7, "  Documents in Contract",                     fill=False, align="L")
        pdf.cell(col_w[1], 7, str(enterprise.no_of_documents),               fill=False, align="C")
        pdf.cell(col_w[2] + col_w[3] + col_w[4], 7, "",                     fill=False)
        pdf.ln()

    pdf.ln(2)

    def _money_row(label: str, amount: float, bold: bool = False, color=None):
        pdf.set_x(110)
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.set_text_color(*(color or (75, 85, 99)))
        pdf.cell(50, 7, label, align="R")
        pdf.set_text_color(*(color or (17, 24, 39)))
        pdf.cell(36, 7, f"BDT {amount:,.2f}", align="R", ln=1)

    _money_row("Total Contract Value:",  enterprise.total_cost)
    _money_row("Advance Billed:",        enterprise.advance_bill,  color=(22, 163, 74))
    pdf.set_x(110)
    pdf.set_draw_color(15, 23, 42)
    pdf.line(110, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(1)
    due_color = (220, 38, 38) if enterprise.due_amount > 0 else (22, 163, 74)
    _money_row("Due Amount:",            enterprise.due_amount,    bold=True, color=due_color)

    # Duration info
    if enterprise.duration_days is not None:
        pdf.ln(4)
        pdf.set_x(110)
        pdf.set_font("Helvetica", "", 8); pdf.set_text_color(100, 116, 139)
        pdf.cell(86, 5, f"Contract Duration: {enterprise.duration_days} days", align="R", ln=1)

    pdf.ln(4)

    pdf.set_fill_color(241, 245, 249)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 7.5); pdf.set_text_color(55, 65, 81)
    pdf.cell(182, 6, "TERMS & CONDITIONS", align="L", fill=True, ln=1)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 8); pdf.set_text_color(75, 85, 99)
    pdf.multi_cell(
        182, 5,
        "1. This invoice covers OCR page quota as outlined above.\n"
        "2. No online payment is accepted for enterprise contracts. "
        "Payment should be settled via direct bank transfer or cheque.\n"
        "3. Pages are non-refundable once consumed.\n"
        "4. For billing queries contact your account manager or accounts@doceanai.cloud.",
        fill=True,
    )
    pdf.set_y(-20)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.set_font("Helvetica", "", 8); pdf.set_text_color(156, 163, 175)
    pdf.set_x(14)
    pdf.cell(182, 8, "DoceanAI  |  accounts@doceanai.cloud  |  doceanai.cloud", align="C")

    # PyFPDF 1.x: output(dest='S') returns the PDF as a str
    # fpdf2:       output()          returns bytearray (no dest param)
    try:
        raw = pdf.output(dest='S')  # PyFPDF 1.x
    except TypeError:
        raw = pdf.output()          # fpdf2
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return raw.encode('latin-1')
