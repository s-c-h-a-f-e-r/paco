# FILE: invoice.py | PURPOSE: Generate PDF invoices and proposals for clients

import os
from datetime import datetime, timedelta
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from . import database as db

INVOICE_DIR = Path(__file__).parent.parent / "data" / "invoices"
INVOICE_DIR.mkdir(exist_ok=True)

PROPOSAL_DIR = Path(__file__).parent.parent / "data" / "proposals"
PROPOSAL_DIR.mkdir(exist_ok=True)


def generate_invoice_number():
    """Generate a unique invoice number."""
    now = datetime.now()
    # Format: INV-YYYYMM-XXX
    prefix = f"INV-{now.strftime('%Y%m')}"

    # Find the next number for this month
    conn = db.get_connection()
    existing = conn.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()

    next_num = len(existing) + 1
    return f"{prefix}-{next_num:03d}"


def generate_invoice(client_id, period_start=None, period_end=None, maintenance_amount=None):
    """Generate a PDF invoice for a client."""
    client = db.get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")

    # Default to current quarter
    if not period_end:
        period_end = datetime.now().date()
    if not period_start:
        # Start of current quarter
        month = ((period_end.month - 1) // 3) * 3 + 1
        period_start = period_end.replace(month=month, day=1)

    # Get uninvoiced services
    services = db.get_client_services(client_id, uninvoiced_only=True)

    # Calculate totals
    services_total = sum(s['price'] or 0 for s in services)
    maintenance = maintenance_amount or 0
    subtotal = maintenance + services_total
    total = subtotal  # No tax for now

    # Generate invoice number
    invoice_number = generate_invoice_number()

    # Create PDF
    pdf_filename = f"{invoice_number}.pdf"
    pdf_path = INVOICE_DIR / pdf_filename

    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)

    elements = []
    styles = getSampleStyleSheet()

    # Header
    header_style = ParagraphStyle('Header', parent=styles['Heading1'],
                                  fontSize=24, spaceAfter=20)
    elements.append(Paragraph("INVOICE", header_style))

    # Business info
    business_style = ParagraphStyle('Business', parent=styles['Normal'],
                                    fontSize=10, textColor=colors.grey)
    elements.append(Paragraph("Hernandez Landscaping", business_style))
    elements.append(Paragraph("Santa Cruz, California", business_style))
    elements.append(Paragraph("(831) 359-6537", business_style))
    elements.append(Spacer(1, 20))

    # Invoice details
    details_data = [
        ["Invoice Number:", invoice_number],
        ["Date:", datetime.now().strftime("%B %d, %Y")],
        ["Period:", f"{period_start.strftime('%b %d, %Y')} - {period_end.strftime('%b %d, %Y')}"],
    ]
    details_table = Table(details_data, colWidths=[1.5*inch, 3*inch])
    details_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 20))

    # Bill To
    elements.append(Paragraph("Bill To:", styles['Heading3']))
    elements.append(Paragraph(client['name'], styles['Normal']))
    if client['address']:
        elements.append(Paragraph(client['address'], styles['Normal']))
    elements.append(Spacer(1, 20))

    # Services table
    elements.append(Paragraph("Services", styles['Heading3']))

    table_data = [["Description", "Date", "Amount"]]

    if maintenance:
        table_data.append([
            "Quarterly Maintenance",
            f"{period_start.strftime('%b')} - {period_end.strftime('%b %Y')}",
            f"${maintenance:,.2f}"
        ])

    for service in services:
        date_str = service['service_date'] if service['service_date'] else ""
        table_data.append([
            service['description'],
            date_str,
            f"${service['price']:,.2f}" if service['price'] else "$0.00"
        ])

    # Add totals
    table_data.append(["", "", ""])
    table_data.append(["", "Subtotal:", f"${subtotal:,.2f}"])
    table_data.append(["", "Total Due:", f"${total:,.2f}"])

    services_table = Table(table_data, colWidths=[4*inch, 1.5*inch, 1.5*inch])
    services_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.grey),
        ('FONTNAME', (1, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (1, -2), (-1, -2), 1, colors.black),
    ]))
    elements.append(services_table)
    elements.append(Spacer(1, 30))

    # Payment info
    elements.append(Paragraph("Payment Information", styles['Heading3']))
    elements.append(Paragraph("Please make payment within 30 days.", styles['Normal']))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))

    # Build PDF
    doc.build(elements)

    # Save invoice to database
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO invoices (client_id, invoice_number, period_start, period_end, subtotal, total, pdf_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (client_id, invoice_number, period_start, period_end, subtotal, total, str(pdf_path)))
    invoice_id = cursor.lastrowid

    # Mark services as invoiced
    for service in services:
        conn.execute(
            "UPDATE services SET invoiced = TRUE, invoice_id = ? WHERE id = ?",
            (invoice_id, service['id'])
        )

    conn.commit()
    conn.close()

    return {
        'invoice_id': invoice_id,
        'invoice_number': invoice_number,
        'pdf_path': str(pdf_path),
        'total': total,
        'services_count': len(services),
        'period': f"{period_start} to {period_end}"
    }


def get_client_invoices(client_id):
    """Get all invoices for a client."""
    conn = db.get_connection()
    invoices = conn.execute("""
        SELECT * FROM invoices WHERE client_id = ? ORDER BY created_at DESC
    """, (client_id,)).fetchall()
    conn.close()
    return [dict(i) for i in invoices]


def generate_invoice_from_proposal(proposal_id):
    """Generate an invoice from an accepted/sent proposal."""
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    client = db.get_client(proposal['client_id'])
    if not client:
        raise ValueError(f"Client not found for proposal")

    # Generate invoice number
    invoice_number = generate_invoice_number()

    # Create PDF
    pdf_filename = f"{invoice_number}.pdf"
    pdf_path = INVOICE_DIR / pdf_filename

    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)

    elements = []
    styles = getSampleStyleSheet()

    # Header
    header_style = ParagraphStyle('Header', parent=styles['Heading1'],
                                  fontSize=24, spaceAfter=20)
    elements.append(Paragraph("INVOICE", header_style))

    # Business info
    business_style = ParagraphStyle('Business', parent=styles['Normal'],
                                    fontSize=10, textColor=colors.grey)
    elements.append(Paragraph("Hernandez Landscaping", business_style))
    elements.append(Paragraph("Santa Cruz, California", business_style))
    elements.append(Paragraph("(831) 359-6537", business_style))
    elements.append(Spacer(1, 20))

    # Invoice details
    details_data = [
        ["Invoice Number:", invoice_number],
        ["Date:", datetime.now().strftime("%B %d, %Y")],
        ["Based on Proposal:", proposal['proposal_number']],
    ]
    details_table = Table(details_data, colWidths=[1.5*inch, 3*inch])
    details_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 20))

    # Bill To
    elements.append(Paragraph("Bill To:", styles['Heading3']))
    elements.append(Paragraph(client['name'], styles['Normal']))
    if client['address']:
        elements.append(Paragraph(client['address'], styles['Normal']))
    elements.append(Spacer(1, 20))

    # Services table
    elements.append(Paragraph("Services", styles['Heading3']))

    table_data = [["Description", "Amount"]]

    services = proposal.get('services', [])
    for service in services:
        table_data.append([
            service.get('description', ''),
            f"${service.get('price', 0):,.2f}"
        ])

    # Add totals
    table_data.append(["", ""])
    table_data.append(["Total Due:", f"${proposal['total']:,.2f}"])

    services_table = Table(table_data, colWidths=[5*inch, 2*inch])
    services_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -3), 0.5, colors.grey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
    ]))
    elements.append(services_table)
    elements.append(Spacer(1, 30))

    # Payment info
    elements.append(Paragraph("Payment Information", styles['Heading3']))
    elements.append(Paragraph("Please make payment within 30 days.", styles['Normal']))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))

    # Build PDF
    doc.build(elements)

    # Save invoice to database
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO invoices (client_id, invoice_number, subtotal, total, pdf_path)
        VALUES (?, ?, ?, ?, ?)
    """, (proposal['client_id'], invoice_number, proposal['total'], proposal['total'], str(pdf_path)))
    invoice_id = cursor.lastrowid

    # Mark proposal as converted to invoice (accepted status)
    conn.execute("UPDATE proposals SET status = 'accepted' WHERE id = ?", (proposal_id,))

    conn.commit()
    conn.close()

    return {
        'invoice_id': invoice_id,
        'invoice_number': invoice_number,
        'pdf_path': str(pdf_path),
        'total': proposal['total'],
        'from_proposal': proposal['proposal_number']
    }


def generate_proposal_pdf(proposal_id):
    """Generate a PDF proposal for a client."""
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    client = db.get_client(proposal['client_id'])
    if not client:
        raise ValueError(f"Client not found for proposal")

    # Create PDF
    pdf_filename = f"{proposal['proposal_number']}.pdf"
    pdf_path = PROPOSAL_DIR / pdf_filename

    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)

    elements = []
    styles = getSampleStyleSheet()

    # Header
    header_style = ParagraphStyle('Header', parent=styles['Heading1'],
                                  fontSize=24, spaceAfter=20, textColor=colors.HexColor('#2d5a27'))
    elements.append(Paragraph("PROPOSAL", header_style))

    # Business info
    business_style = ParagraphStyle('Business', parent=styles['Normal'],
                                    fontSize=10, textColor=colors.grey)
    elements.append(Paragraph("Hernandez Landscaping", business_style))
    elements.append(Paragraph("Santa Cruz, California", business_style))
    elements.append(Paragraph("(831) 359-6537", business_style))
    elements.append(Spacer(1, 20))

    # Proposal details
    details_data = [
        ["Proposal Number:", proposal['proposal_number']],
        ["Date:", datetime.now().strftime("%B %d, %Y")],
        ["Valid Until:", proposal['valid_until'] if proposal['valid_until'] else "30 days"],
    ]
    details_table = Table(details_data, colWidths=[1.5*inch, 3*inch])
    details_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 20))

    # Prepared For
    elements.append(Paragraph("Prepared For:", styles['Heading3']))
    elements.append(Paragraph(client['name'], styles['Normal']))
    if client['address']:
        elements.append(Paragraph(client['address'], styles['Normal']))
    if client['phone']:
        elements.append(Paragraph(f"Phone: {client['phone']}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Services table
    elements.append(Paragraph("Proposed Services", styles['Heading3']))

    table_data = [["Description", "Price"]]

    services = proposal.get('services', [])
    for service in services:
        table_data.append([
            service.get('description', ''),
            f"${service.get('price', 0):,.2f}"
        ])

    # Add totals
    table_data.append(["", ""])
    table_data.append(["Total:", f"${proposal['total']:,.2f}"])

    services_table = Table(table_data, colWidths=[5*inch, 2*inch])
    services_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5a27')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -3), 0.5, colors.grey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
    ]))
    elements.append(services_table)
    elements.append(Spacer(1, 20))

    # Notes
    if proposal.get('notes'):
        elements.append(Paragraph("Notes:", styles['Heading3']))
        elements.append(Paragraph(proposal['notes'], styles['Normal']))
        elements.append(Spacer(1, 20))

    # Terms
    elements.append(Paragraph("Terms & Conditions", styles['Heading3']))
    terms_style = ParagraphStyle('Terms', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
    elements.append(Paragraph("• This proposal is valid for 30 days from the date above.", terms_style))
    elements.append(Paragraph("• A 50% deposit is required to schedule work.", terms_style))
    elements.append(Paragraph("• Final payment is due upon completion.", terms_style))
    elements.append(Spacer(1, 20))

    # Acceptance
    elements.append(Paragraph("To accept this proposal, please sign below:", styles['Normal']))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("_" * 40, styles['Normal']))
    elements.append(Paragraph("Signature                                    Date", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Thank you
    elements.append(Paragraph("Thank you for considering Hernandez Landscaping!", styles['Normal']))

    # Build PDF
    doc.build(elements)

    # Update proposal with PDF path
    db.update_proposal_pdf(proposal_id, str(pdf_path))

    return {
        'proposal_id': proposal_id,
        'proposal_number': proposal['proposal_number'],
        'pdf_path': str(pdf_path),
        'total': proposal['total']
    }
