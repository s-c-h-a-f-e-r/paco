# FILE: messaging.py | PURPOSE: Send SMS via Twilio and emails via SendGrid for client communication

import os
from typing import Optional

# Twilio
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False


# Configuration - set these in environment or .env
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Jaime's Twilio number

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "jhlandscaping002@gmail.com")
FROM_NAME = os.getenv("FROM_NAME", "Hernandez Landscaping")


def send_sms(to_phone: str, message: str) -> dict:
    """
    Send SMS via Twilio.

    Args:
        to_phone: Recipient phone number (e.g., "+18315551234")
        message: Text message content

    Returns:
        dict with 'success', 'message_sid' or 'error'
    """
    if not TWILIO_AVAILABLE:
        return {"success": False, "error": "Twilio not installed. Run: pip install twilio"}

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return {"success": False, "error": "Twilio credentials not configured"}

    # Normalize phone number
    phone = normalize_phone(to_phone)
    if not phone:
        return {"success": False, "error": f"Invalid phone number: {to_phone}"}

    try:
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )
        return {"success": True, "message_sid": msg.sid, "status": msg.status}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_email(to_email: str, subject: str, body: str, html_body: Optional[str] = None) -> dict:
    """
    Send email via SendGrid.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Plain text body
        html_body: Optional HTML body

    Returns:
        dict with 'success' or 'error'
    """
    if not SENDGRID_AVAILABLE:
        return {"success": False, "error": "SendGrid not installed. Run: pip install sendgrid"}

    if not SENDGRID_API_KEY:
        return {"success": False, "error": "SendGrid API key not configured"}

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)

        from_email = Email(FROM_EMAIL, FROM_NAME)
        to_email_obj = To(to_email)
        content = Content("text/plain", body)

        mail = Mail(from_email, to_email_obj, subject, content)

        if html_body:
            mail.add_content(Content("text/html", html_body))

        response = sg.send(mail)

        if response.status_code in [200, 201, 202]:
            return {"success": True, "status_code": response.status_code}
        else:
            return {"success": False, "error": f"SendGrid returned {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def normalize_phone(phone: str) -> Optional[str]:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX for US).

    Args:
        phone: Phone number in any format

    Returns:
        Normalized phone number or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digits
    digits = ''.join(c for c in phone if c.isdigit())

    # Handle US numbers
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif len(digits) > 10 and phone.startswith('+'):
        return f"+{digits}"

    return None


def send_to_client(client: dict, message: str, subject: Optional[str] = None,
                   message_type: str = "text") -> dict:
    """
    Send message to client via appropriate channel.

    Args:
        client: Client dict with phone, email, contact_preference
        message: Message content
        subject: Email subject (for emails)
        message_type: "text" for SMS, "email" for email-only (proposals/invoices)

    Returns:
        dict with results for each channel attempted
    """
    results = {"sms": None, "email": None}

    # Proposals and invoices always go via email
    if message_type == "email":
        if client.get("email"):
            email_subject = subject or "Message from Hernandez Landscaping"
            html_body = create_email_html(message, client.get("name", ""))
            results["email"] = send_email(client["email"], email_subject, message, html_body)
        else:
            results["email"] = {"success": False, "error": "No email address for client"}
    else:
        # Regular messages go via SMS
        if client.get("phone"):
            results["sms"] = send_sms(client["phone"], message)
        else:
            results["sms"] = {"success": False, "error": "No phone number for client"}

    # Overall success
    results["success"] = (
        (results["sms"] and results["sms"].get("success")) or
        (results["email"] and results["email"].get("success"))
    )

    return results


def send_proposal_email(client: dict, proposal: dict, pdf_path: str) -> dict:
    """
    Send a proposal via email with PDF attachment.

    Args:
        client: Client dict with name, email
        proposal: Proposal dict with proposal_number, total
        pdf_path: Path to the PDF file

    Returns:
        dict with success status
    """
    if not SENDGRID_AVAILABLE:
        return {"success": False, "error": "SendGrid not installed"}

    if not SENDGRID_API_KEY:
        return {"success": False, "error": "SendGrid not configured"}

    if not client.get("email"):
        return {"success": False, "error": "No email address for client"}

    try:
        import base64
        from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition

        sg = SendGridAPIClient(SENDGRID_API_KEY)

        # Read and encode PDF
        with open(pdf_path, "rb") as f:
            pdf_data = base64.b64encode(f.read()).decode()

        subject = f"Proposal {proposal['proposal_number']} from Hernandez Landscaping"
        body = f"""Hi {client.get('name', 'there')},

Please find attached our proposal for your landscaping project.

Proposal #: {proposal['proposal_number']}
Total: ${proposal['total']:.2f}

If you have any questions, please don't hesitate to reach out.

Thank you for your business!

Best regards,
Hernandez Landscaping
"""

        html_body = create_email_html(body, client.get('name', ''))

        from_email = Email(FROM_EMAIL, FROM_NAME)
        to_email = To(client["email"])

        mail = Mail(from_email, to_email, subject, Content("text/plain", body))
        mail.add_content(Content("text/html", html_body))

        # Attach PDF
        attachment = Attachment()
        attachment.file_content = FileContent(pdf_data)
        attachment.file_type = FileType("application/pdf")
        attachment.file_name = FileName(f"{proposal['proposal_number']}.pdf")
        attachment.disposition = Disposition("attachment")
        mail.add_attachment(attachment)

        response = sg.send(mail)

        if response.status_code in [200, 201, 202]:
            return {"success": True}
        else:
            return {"success": False, "error": f"SendGrid returned {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def send_invoice_email(client: dict, invoice: dict, pdf_path: str) -> dict:
    """
    Send an invoice via email with PDF attachment.

    Args:
        client: Client dict with name, email
        invoice: Invoice dict with invoice_number, total
        pdf_path: Path to the PDF file

    Returns:
        dict with success status
    """
    if not SENDGRID_AVAILABLE:
        return {"success": False, "error": "SendGrid not installed"}

    if not SENDGRID_API_KEY:
        return {"success": False, "error": "SendGrid not configured"}

    if not client.get("email"):
        return {"success": False, "error": "No email address for client"}

    try:
        import base64
        from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition

        sg = SendGridAPIClient(SENDGRID_API_KEY)

        # Read and encode PDF
        with open(pdf_path, "rb") as f:
            pdf_data = base64.b64encode(f.read()).decode()

        subject = f"Invoice {invoice['invoice_number']} from Hernandez Landscaping"
        body = f"""Hi {client.get('name', 'there')},

Please find attached your invoice for landscaping services.

Invoice #: {invoice['invoice_number']}
Total: ${invoice['total']:.2f}

Payment is due within 30 days. Thank you for your business!

Best regards,
Hernandez Landscaping
"""

        html_body = create_email_html(body, client.get('name', ''))

        from_email = Email(FROM_EMAIL, FROM_NAME)
        to_email = To(client["email"])

        mail = Mail(from_email, to_email, subject, Content("text/plain", body))
        mail.add_content(Content("text/html", html_body))

        # Attach PDF
        attachment = Attachment()
        attachment.file_content = FileContent(pdf_data)
        attachment.file_type = FileType("application/pdf")
        attachment.file_name = FileName(f"{invoice['invoice_number']}.pdf")
        attachment.disposition = Disposition("attachment")
        mail.add_attachment(attachment)

        response = sg.send(mail)

        if response.status_code in [200, 201, 202]:
            return {"success": True}
        else:
            return {"success": False, "error": f"SendGrid returned {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def create_email_html(message: str, client_name: str) -> str:
    """Create a nice HTML email template."""
    # Escape HTML in message
    import html
    safe_message = html.escape(message).replace('\n', '<br>')

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
        <div style="background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 24px;">
                <h1 style="color: #15803D; margin: 0; font-size: 24px;">Hernandez Landscaping</h1>
                <p style="color: #666; margin: 4px 0 0 0; font-size: 14px;">Professional Landscaping Services</p>
            </div>

            <div style="border-top: 1px solid #eee; padding-top: 20px;">
                <p style="color: #333; font-size: 16px; line-height: 1.6; margin: 0;">
                    {safe_message}
                </p>
            </div>

            <div style="border-top: 1px solid #eee; margin-top: 24px; padding-top: 20px; text-align: center;">
                <p style="color: #888; font-size: 13px; margin: 0;">
                    Questions? Reply to this email or call us at (831) 359-6537
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def check_configuration() -> dict:
    """Check which messaging services are configured."""
    return {
        "twilio": {
            "installed": TWILIO_AVAILABLE,
            "configured": all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER])
        },
        "sendgrid": {
            "installed": SENDGRID_AVAILABLE,
            "configured": bool(SENDGRID_API_KEY)
        }
    }
