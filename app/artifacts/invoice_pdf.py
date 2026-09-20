"""Professional GST Tax Invoice PDF Generator using ReportLab."""

import os
from pathlib import Path
from typing import Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from app.config import settings
from app.database.models import Bill, OwnerPreference


def generate_invoice_pdf(bill_id: int, session: Session, output_path: Optional[str] = None) -> str:
    """
    Generate a professional Indian GST Tax Invoice PDF using ReportLab.
    Returns the absolute path to the generated PDF file.
    """
    bill = session.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise ValueError(f"Bill with ID {bill_id} not found.")

    # Retrieve shop settings from preferences
    def get_pref(key: str, default: str) -> str:
        pref = session.query(OwnerPreference).filter(OwnerPreference.key == key).first()
        return pref.value if pref else default

    shop_name = get_pref("shop_name", settings.DEFAULT_SHOP_NAME)
    gstin = get_pref("gstin", settings.DEFAULT_GSTIN)
    address = get_pref("address", settings.DEFAULT_SHOP_ADDRESS)
    phone = get_pref("phone", settings.DEFAULT_SHOP_PHONE)

    # Output file path
    artifacts_dir = settings.ensure_artifacts_dir()
    if not output_path:
        filename = f"Invoice_{bill.bill_number.replace('/', '_')}.pdf"
        output_path = str(artifacts_dir / filename)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ShopTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        alignment=1,  # Center
    )
    sub_title_style = ParagraphStyle(
        "ShopSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4A5568"),
        alignment=1,
    )
    badge_style = ParagraphStyle(
        "InvoiceBadge",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#2B6CB0"),
        alignment=1,
    )
    cell_style = ParagraphStyle(
        "CellNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
    )
    cell_right = ParagraphStyle(
        "CellRight",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=2,  # Right
    )
    cell_right_bold = ParagraphStyle(
        "CellRightBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=2,
    )

    story = []

    # 1. Header
    story.append(Paragraph(shop_name.upper(), title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{address} | Phone: {phone}", sub_title_style))
    story.append(Paragraph(f"<b>GSTIN:</b> {gstin}", sub_title_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#CBD5E0")))
    story.append(Spacer(1, 8))

    # 2. Tax Invoice Title
    badge_text = "TAX INVOICE" if bill.status == "FINALIZED" else "DRAFT ESTIMATE (PRO-FORMA)"
    story.append(Paragraph(badge_text, badge_style))
    story.append(Spacer(1, 8))

    # 3. Bill & Customer Metadata Table
    bill_date = (bill.finalized_at or bill.created_at).strftime("%d-%b-%Y %I:%M %p")
    cust_name = bill.customer.name if bill.customer else "Walk-in Customer"
    cust_phone = bill.customer.phone if bill.customer and bill.customer.phone else "N/A"

    meta_data = [
        [
            Paragraph(f"<b>Invoice No:</b> {bill.bill_number}", cell_style),
            Paragraph(f"<b>Customer:</b> {cust_name}", cell_style),
        ],
        [
            Paragraph(f"<b>Date & Time:</b> {bill_date}", cell_style),
            Paragraph(f"<b>Customer Phone:</b> {cust_phone}", cell_style),
        ],
        [
            Paragraph(f"<b>Payment Mode:</b> {bill.payment_mode}", cell_style),
            Paragraph(f"<b>Payment Ref:</b> {bill.payment_reference or 'Direct'}", cell_style),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # 4. Itemized Table
    # Headers: #, Item Description, HSN, Qty, Unit Price, Taxable, GST %, CGST, SGST, Total
    headers = [
        Paragraph("<b>#</b>", cell_bold),
        Paragraph("<b>Item Description</b>", cell_bold),
        Paragraph("<b>HSN</b>", cell_bold),
        Paragraph("<b>Qty</b>", cell_right_bold),
        Paragraph("<b>Rate</b>", cell_right_bold),
        Paragraph("<b>Taxable</b>", cell_right_bold),
        Paragraph("<b>GST</b>", cell_right_bold),
        Paragraph("<b>CGST</b>", cell_right_bold),
        Paragraph("<b>SGST</b>", cell_right_bold),
        Paragraph("<b>Total (₹)</b>", cell_right_bold),
    ]
    table_data = [headers]

    for idx, item in enumerate(bill.items, 1):
        p_name = item.product.name if item.product else "Item"
        hsn = item.product.hsn_code if item.product else "-"
        unit = item.product.unit if item.product else ""
        qty_str = f"{item.quantity:g} {unit}"

        row = [
            Paragraph(str(idx), cell_style),
            Paragraph(p_name, cell_style),
            Paragraph(hsn, cell_style),
            Paragraph(qty_str, cell_right),
            Paragraph(f"₹{item.unit_price:.2f}", cell_right),
            Paragraph(f"₹{item.taxable_amount:.2f}", cell_right),
            Paragraph(f"{item.gst_rate:g}%", cell_right),
            Paragraph(f"₹{item.cgst:.2f}", cell_right),
            Paragraph(f"₹{item.sgst:.2f}", cell_right),
            Paragraph(f"₹{item.total:.2f}", cell_right),
        ]
        table_data.append(row)

    # Empty item safety
    if not bill.items:
        table_data.append([
            Paragraph("1", cell_style),
            Paragraph("No items added yet", cell_style),
            Paragraph("-", cell_style),
            Paragraph("0", cell_right),
            Paragraph("₹0.00", cell_right),
            Paragraph("₹0.00", cell_right),
            Paragraph("0%", cell_right),
            Paragraph("₹0.00", cell_right),
            Paragraph("₹0.00", cell_right),
            Paragraph("₹0.00", cell_right),
        ])

    col_widths = [20, 140, 40, 45, 45, 52, 35, 45, 45, 55]
    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(items_table)
    story.append(Spacer(1, 10))

    # 5. Financial Summary Box
    summary_data = [
        [Paragraph("Taxable Subtotal:", cell_right_bold), Paragraph(f"₹{bill.subtotal:.2f}", cell_right)],
        [Paragraph("Central GST (CGST):", cell_right_bold), Paragraph(f"₹{bill.cgst:.2f}", cell_right)],
        [Paragraph("State GST (SGST):", cell_right_bold), Paragraph(f"₹{bill.sgst:.2f}", cell_right)],
        [Paragraph("Total GST Tax:", cell_right_bold), Paragraph(f"₹{bill.total_tax:.2f}", cell_right)],
        [Paragraph("<b>Grand Total:</b>", cell_right_bold), Paragraph(f"<b>₹{bill.grand_total:.2f}</b>", cell_right_bold)],
    ]
    summary_table = Table(summary_data, colWidths=[380, 142])
    summary_table.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#2B6CB0")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EBF8FF")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # 6. Terms & Footer
    footer_text = "Thank you for shopping with us! Returns accepted within 24 hours with original bill."
    story.append(Paragraph(footer_text, sub_title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("This is a computer-generated tax invoice and requires no physical signature.", sub_title_style))

    doc.build(story)
    return output_path
