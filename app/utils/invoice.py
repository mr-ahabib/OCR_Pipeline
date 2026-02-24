"""Invoice PDF generator — uses fpdf2 (already in requirements.txt)."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

from fpdf import FPDF


def generate_invoice_pdf(
    invoice_number: str,
    user_full_name: str,
    user_email: str,
    pages_purchased: int,
    payment_amount: float,
    currency: str,
    paid_at: Optional[datetime] = None,
) -> bytes:
    """
    Generate a professional invoice PDF for a DoceanAI subscription payment.
    Returns raw PDF bytes ready for email attachment or download.
    """
    date_str = (paid_at or datetime.utcnow()).strftime("%B %d, %Y")
    time_str = (paid_at or datetime.utcnow()).strftime("%I:%M %p UTC")
    cost_per_page = payment_amount / pages_purchased if pages_purchased else 0

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    # ── Header band ────────────────────────────────────────────────────────────
    pdf.set_fill_color(15, 23, 42)    # dark navy
    pdf.rect(0, 0, 210, 38, "F")

    # Brand name
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(14, 9)
    pdf.cell(120, 12, "DoceanAI", ln=0)

    # INVOICE label
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(148, 163, 184)
    pdf.set_xy(14, 23)
    pdf.cell(120, 8, "AI-Powered OCR Platform", ln=0)

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(140, 9)
    pdf.cell(56, 10, "INVOICE", align="R", ln=0)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.set_xy(140, 23)
    pdf.cell(56, 8, f"#{invoice_number}", align="R", ln=1)

    pdf.set_y(46)

    # ── Meta row ───────────────────────────────────────────────────────────────
    pdf.set_text_color(55, 65, 81)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(241, 245, 249)
    # Left: bill to
    pdf.set_x(14)
    pdf.cell(85, 6, "BILLED TO", ln=0, fill=False)
    # Right: invoice meta
    pdf.set_x(110)
    pdf.cell(86, 6, "INVOICE DETAILS", ln=1, fill=False)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(17, 24, 39)
    pdf.set_x(14)
    pdf.cell(85, 7, user_full_name or "-", ln=0)
    pdf.set_x(110)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(40, 6, "Invoice No:", ln=0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(46, 6, invoice_number, ln=1)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(75, 85, 99)
    pdf.set_x(14)
    pdf.cell(85, 6, user_email, ln=0)
    pdf.set_x(110)
    pdf.cell(40, 6, "Date Issued:", ln=0)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(46, 6, date_str, ln=1)

    pdf.set_x(110)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(40, 6, "Time:", ln=0)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(46, 6, time_str, ln=1)

    pdf.set_x(110)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(40, 6, "Status:", ln=0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(22, 163, 74)   # green
    pdf.cell(46, 6, "PAID", ln=1)

    pdf.ln(6)

    # ── Divider ────────────────────────────────────────────────────────────────
    pdf.set_draw_color(229, 231, 235)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(6)

    # ── Line items table ───────────────────────────────────────────────────────
    # Header
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    col_w = [90, 30, 36, 36]
    headers = ["Description", "Pages", "Unit Price", "Total"]
    aligns = ["L", "C", "R", "R"]
    pdf.set_x(14)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, fill=True, align=aligns[i])
    pdf.ln()

    # Row
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(17, 24, 39)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(14)
    pdf.cell(col_w[0], 8, "DoceanAI OCR Subscription", fill=True, align="L")
    pdf.cell(col_w[1], 8, str(pages_purchased), fill=True, align="C")
    pdf.cell(col_w[2], 8, f"{currency} {cost_per_page:.2f}", fill=True, align="R")
    pdf.cell(col_w[3], 8, f"{currency} {payment_amount:.2f}", fill=True, align="R")
    pdf.ln()

    pdf.ln(4)

    # ── Totals ─────────────────────────────────────────────────────────────────
    def _total_row(label: str, value: str, bold: bool = False, color=None):
        pdf.set_x(110)
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.set_text_color(*(color or (75, 85, 99)))
        pdf.cell(40, 7, label, align="R")
        pdf.set_text_color(*(color or (17, 24, 39)))
        pdf.cell(46, 7, value, align="R", ln=1)

    _total_row("Subtotal:", f"{currency} {payment_amount:.2f}")
    _total_row("Tax / VAT:", "Included")
    pdf.set_x(110)
    pdf.set_draw_color(15, 23, 42)
    pdf.line(110, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(1)
    _total_row("Total Paid:", f"{currency} {payment_amount:.2f}", bold=True, color=(15, 23, 42))

    pdf.ln(10)

    # ── Thank you note ─────────────────────────────────────────────────────────
    pdf.set_fill_color(241, 245, 249)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(75, 85, 99)
    pdf.multi_cell(
        182, 5,
        "Thank you for subscribing to DoceanAI! Your OCR pages have been credited to your "
        "account and are ready to use. For support contact us at support@doceanai.cloud.",
        fill=True,
    )

    # ── Footer ─────────────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(156, 163, 175)
    pdf.set_x(14)
    pdf.cell(182, 8, "DoceanAI  |  support@doceanai.cloud  |  doceanai.cloud", align="C")

    # Return bytes
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
