from __future__ import annotations

import io


def _format_money(cents: int, currency: str) -> str:
    amount = cents / 100
    return f"{currency} {amount:,.2f}"


def render_invoice_pdf(*, invoice, tenant, line_items: list) -> bytes:
    """Render a simple invoice PDF and return bytes.

    ReportLab is imported lazily to keep startup light and allow optional installs.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError("PDF rendering requires reportlab package") from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    y = height - 48
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(48, y, "CliniGraph AI Invoice")

    y -= 26
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, y, f"Tenant: {tenant.name}")
    y -= 14
    pdf.drawString(48, y, f"Invoice ID: {invoice.invoice_id}")
    y -= 14
    pdf.drawString(48, y, f"Period: {invoice.period_start.isoformat()} - {invoice.period_end.isoformat()}")
    y -= 14
    pdf.drawString(48, y, f"Currency: {invoice.currency}")
    y -= 14
    pdf.drawString(48, y, f"Status: {invoice.status}")
    y -= 14
    pdf.drawString(48, y, f"Generated: {invoice.generated_at.isoformat()}")

    y -= 22
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(48, y, "Description")
    pdf.drawString(300, y, "Qty")
    pdf.drawString(360, y, "Unit")
    pdf.drawString(470, y, "Total")

    y -= 10
    pdf.line(48, y, width - 48, y)

    pdf.setFont("Helvetica", 10)
    y -= 16
    for line in line_items:
        if y < 72:
            pdf.showPage()
            y = height - 48
            pdf.setFont("Helvetica", 10)
        pdf.drawString(48, y, str(line.description)[:42])
        pdf.drawRightString(330, y, str(line.quantity))
        pdf.drawRightString(430, y, _format_money(int(line.unit_price_cents), invoice.currency))
        pdf.drawRightString(540, y, _format_money(int(line.total_price_cents), invoice.currency))
        y -= 14

    y -= 8
    pdf.line(48, y, width - 48, y)
    y -= 18
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(48, y, "Total:")
    pdf.drawRightString(540, y, _format_money(int(invoice.total_cents), invoice.currency))

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()