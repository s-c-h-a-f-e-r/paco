# FILE: main.py | PURPOSE: FastAPI server for Jardín web app

import os
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Depends, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
import tempfile
import openai
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from . import database as db
from . import ai
from . import invoice
from . import messaging
from . import auth

load_dotenv()

app = FastAPI(title="Jardín", description="AI Business Assistant for Landscaping")

# Setup default users on startup
@app.on_event("startup")
async def startup():
    created = auth.setup_default_users()
    if created:
        print(f"Created default users: {created}")

# Serve static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")


# Request/Response models
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[int] = None


class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    language: str = 'en'
    contact_preference: str = 'sms'  # 'sms', 'email', or 'both'
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    contact_preference: Optional[str] = None
    notes: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


# Auth dependency
async def get_current_user(session: Optional[str] = Cookie(None)):
    """Get current user from session cookie."""
    if not session:
        return None
    return auth.get_session_user(session)


async def require_auth(session: Optional[str] = Cookie(None)):
    """Require authentication - raises 401 if not logged in."""
    user = await get_current_user(session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


class ServiceCreate(BaseModel):
    client_id: int
    description: str
    price: float
    notes: Optional[str] = None


class InvoiceRequest(BaseModel):
    client_id: int
    maintenance_amount: Optional[float] = None
    proposal_id: Optional[int] = None  # Create invoice from accepted proposal


class ProposalCreate(BaseModel):
    client_id: int
    services: list  # [{"description": "...", "price": X}, ...]
    notes: Optional[str] = None


# Routes
@app.get("/")
async def root(session: Optional[str] = Cookie(None)):
    """Serve login page or main app based on auth status."""
    user = auth.get_session_user(session) if session else None
    if user:
        return FileResponse(static_path / "index.html")
    return FileResponse(static_path / "login.html")


@app.get("/api/me")
async def get_me(user: dict = Depends(require_auth)):
    """Get current logged-in user."""
    return {"user": user}


@app.post("/api/login")
async def login(request: LoginRequest, response: Response):
    """Login and create session."""
    user = auth.verify_password(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrecta")

    token = auth.create_session(user["id"])
    # Detect if running on HTTPS (production)
    is_https = os.getenv("RENDER") is not None
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 1 week
        samesite="lax",
        secure=is_https
    )

    # Notify Justin when Jaime or Erika logs in
    if request.username in ["jaime", "erika"]:
        try:
            from datetime import datetime
            messaging.send_email(
                to_email="justinfschafer@gmail.com",
                subject=f"Paco: {user['name']} just logged in",
                body=f"{user['name']} logged into Paco at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC.\n\nThis is an automated notification."
            )
        except Exception:
            pass  # Don't fail login if notification fails

    return {"message": "Bienvenido", "user": {"id": user["id"], "name": user["name"]}}


@app.post("/api/logout")
async def logout(response: Response, session: Optional[str] = Cookie(None)):
    """Logout and clear session."""
    if session:
        auth.logout(session)
    response.delete_cookie("session")
    return {"message": "Hasta luego"}


@app.post("/api/chat")
async def chat(message: ChatMessage):
    """Process a message from Jaime."""
    try:
        result = ai.chat(message.message, session_id=message.session_id)
        return {
            "response": result['text'],
            "client_messages": result['client_messages'],
            "services": result['services'],
            "new_clients": result.get('new_clients', []),
            "proposals": result.get('proposals', []),
            "session_id": result.get('session_id')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients")
async def get_clients():
    """Get all clients."""
    clients = db.get_all_clients()
    return {"clients": clients}


@app.post("/api/clients")
async def create_client(client: ClientCreate):
    """Create a new client."""
    client_id = db.create_client(
        name=client.name,
        phone=client.phone,
        email=client.email,
        address=client.address,
        language=client.language,
        notes=client.notes
    )
    return {"client_id": client_id, "message": "Cliente creado"}


@app.get("/api/clients/{client_id}")
async def get_client(client_id: int):
    """Get a specific client."""
    client = db.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return client


@app.get("/api/clients/{client_id}/services")
async def get_client_services(client_id: int):
    """Get services for a client."""
    services = db.get_client_services(client_id)
    return {"services": services}


@app.post("/api/services")
async def add_service(service: ServiceCreate):
    """Add a service for a client."""
    service_id = db.add_service(
        client_id=service.client_id,
        description=service.description,
        price=service.price,
        notes=service.notes
    )
    # Also update price book
    db.set_price(service.description, service.price)
    return {"service_id": service_id, "message": "Servicio registrado"}


@app.get("/api/prices")
async def get_prices():
    """Get the price book."""
    prices = db.get_all_prices()
    return {"prices": prices}


@app.get("/api/messages/pending")
async def get_pending_messages():
    """Get pending messages to clients."""
    messages = db.get_pending_messages()
    return {"messages": messages}


@app.get("/api/messages")
async def get_all_messages():
    """Get all messages (sent, pending, failed)."""
    messages = db.get_all_messages()
    return {"messages": messages}


class MessageCreate(BaseModel):
    client_id: int
    content: str
    channel: str = 'sms'
    subject: Optional[str] = None


@app.post("/api/messages")
async def create_message(msg: MessageCreate):
    """Create a new message to send to a client."""
    client = db.get_client(msg.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    message_id = db.queue_client_message(
        client_id=msg.client_id,
        content=msg.content,
        channel=msg.channel,
        subject=msg.subject
    )
    return {"message_id": message_id, "status": "pending"}


@app.post("/api/messages/{message_id}/send")
async def send_message(message_id: int):
    """Actually send a message via SMS and/or email."""
    message = db.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")

    # Build client dict for messaging
    client = {
        "name": message["client_name"],
        "phone": message["client_phone"],
        "email": message["client_email"],
        "contact_preference": message.get("contact_preference", "sms")
    }

    # Send via configured channels
    result = messaging.send_to_client(
        client=client,
        message=message["content"],
        subject=message.get("subject")
    )

    if result["success"]:
        db.mark_message_sent(message_id)
        return {
            "message": "Mensaje enviado",
            "sms": result.get("sms"),
            "email": result.get("email")
        }
    else:
        # Collect error messages
        errors = []
        if result.get("sms") and not result["sms"].get("success"):
            errors.append(f"SMS: {result['sms'].get('error')}")
        if result.get("email") and not result["email"].get("success"):
            errors.append(f"Email: {result['email'].get('error')}")

        error_msg = "; ".join(errors) if errors else "Unknown error"
        db.mark_message_failed(message_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/messaging/config")
async def get_messaging_config():
    """Check which messaging services are configured."""
    return messaging.check_configuration()


@app.patch("/api/clients/{client_id}")
async def update_client(client_id: int, update: ClientUpdate):
    """Update a client."""
    client = db.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    updates = {k: v for k, v in update.dict().items() if v is not None}
    if updates:
        db.update_client(client_id, **updates)
    return {"message": "Cliente actualizado"}


@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int):
    """Delete a client and all related data."""
    client = db.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    db.delete_client(client_id)
    return {"message": "Cliente eliminado", "success": True}


@app.post("/api/invoices")
async def create_invoice(request: InvoiceRequest):
    """Generate an invoice for a client."""
    try:
        if request.proposal_id:
            # Create invoice from proposal
            result = invoice.generate_invoice_from_proposal(
                proposal_id=request.proposal_id
            )
        else:
            # Regular maintenance invoice
            result = invoice.generate_invoice(
                client_id=request.client_id,
                maintenance_amount=request.maintenance_amount
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/invoices")
async def get_invoices():
    """Get all invoices."""
    invoices = db.get_all_invoices()
    return {"invoices": invoices}


@app.get("/api/invoices/{invoice_number}/pdf")
async def get_invoice_pdf(invoice_number: str):
    """Download an invoice PDF."""
    pdf_path = invoice.INVOICE_DIR / f"{invoice_number}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Invoice not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{invoice_number}.pdf")


@app.post("/api/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: int):
    """Send an invoice to the client via email."""
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        client = db.get_client(inv['client_id'])
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

        if not client.get('email'):
            raise HTTPException(status_code=400, detail="El cliente no tiene email")

        pdf_path = invoice.INVOICE_DIR / f"{inv['invoice_number']}.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF no encontrado")

        send_result = messaging.send_invoice_email(
            client={"name": client['name'], "email": client['email']},
            invoice={"invoice_number": inv['invoice_number'], "total": inv['total']},
            pdf_path=str(pdf_path)
        )

        if send_result.get("success"):
            db.update_invoice_status(invoice_id, 'sent')
            return {"message": f"Factura enviada a {client['email']}", "success": True}
        else:
            raise HTTPException(status_code=500, detail=send_result.get("error", "Error enviando email"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/invoices/{invoice_id}/paid")
async def mark_invoice_paid(invoice_id: int):
    """Mark an invoice as paid."""
    inv = db.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    db.update_invoice_status(invoice_id, 'paid')
    return {"message": "Factura marcada como pagada", "success": True}


@app.get("/api/conversation")
async def get_conversation(session_id: Optional[int] = None):
    """Get recent conversation history for a session."""
    if session_id:
        messages = db.get_session_messages(session_id)
    else:
        messages = db.get_recent_messages(50)
    return {"messages": messages}


# Chat sessions
@app.get("/api/chats")
async def get_chats():
    """Get all chat sessions."""
    sessions = db.get_chat_sessions()
    return {"sessions": sessions}


@app.post("/api/chats")
async def create_chat(title: Optional[str] = None):
    """Create a new chat session."""
    session_id = db.create_chat_session(title)
    return {"session_id": session_id}


@app.get("/api/chats/{session_id}")
async def get_chat(session_id: int):
    """Get a specific chat session with messages."""
    session = db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat no encontrado")
    messages = db.get_session_messages(session_id)
    return {"session": session, "messages": messages}


@app.delete("/api/chats/{session_id}")
async def delete_chat(session_id: int):
    """Delete a chat session."""
    session = db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat no encontrado")
    db.delete_chat_session(session_id)
    return {"message": "Chat eliminado", "success": True}


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe audio using OpenAI Whisper API."""
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY no configurado", "text": ""}

    try:
        # Get file extension from filename
        filename = audio.filename or "audio.webm"
        ext = filename.split('.')[-1] if '.' in filename else 'webm'

        # Save uploaded audio to temp file
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            content = await audio.read()
            if len(content) == 0:
                return {"error": "Audio vacio", "text": ""}
            tmp.write(content)
            tmp_path = tmp.name

        # Call Whisper API
        client = openai.OpenAI(api_key=api_key)
        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"  # Spanish
            )

        # Clean up temp file
        os.unlink(tmp_path)

        return {"text": transcript.text}

    except Exception as e:
        # Clean up temp file if it exists
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        return {"error": str(e), "text": ""}


# Proposal endpoints
@app.get("/api/proposals")
async def get_proposals():
    """Get all proposals."""
    proposals = db.get_all_proposals()
    return {"proposals": proposals}


@app.post("/api/proposals")
async def create_proposal(request: ProposalCreate):
    """Create a proposal for a client."""
    try:
        total = sum(s.get('price', 0) for s in request.services)
        proposal_id = db.create_proposal(
            client_id=request.client_id,
            services=request.services,
            total=total,
            notes=request.notes
        )
        # Generate PDF
        result = invoice.generate_proposal_pdf(proposal_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/proposals/{proposal_id}/pdf")
async def get_proposal_pdf(proposal_id: int):
    """Generate and download a proposal PDF."""
    try:
        proposal = db.get_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Generate PDF if not exists
        if not proposal.get('pdf_path') or not Path(proposal['pdf_path']).exists():
            result = invoice.generate_proposal_pdf(proposal_id)
            pdf_path = result['pdf_path']
        else:
            pdf_path = proposal['pdf_path']

        return FileResponse(pdf_path, media_type="application/pdf",
                           filename=f"{proposal['proposal_number']}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/proposals/{proposal_id}/send")
async def send_proposal(proposal_id: int):
    """Send a proposal to the client via email."""
    try:
        proposal = db.get_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")

        client = db.get_client(proposal['client_id'])
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

        if not client.get('email'):
            raise HTTPException(status_code=400, detail="El cliente no tiene email. Agrega un email primero.")

        # Generate PDF if not exists
        if not proposal.get('pdf_path') or not Path(proposal['pdf_path']).exists():
            result = invoice.generate_proposal_pdf(proposal_id)
            pdf_path = result['pdf_path']
        else:
            pdf_path = proposal['pdf_path']

        # Send email with PDF attachment
        send_result = messaging.send_proposal_email(
            client={"name": client['name'], "email": client['email']},
            proposal={"proposal_number": proposal['proposal_number'], "total": proposal['total']},
            pdf_path=pdf_path
        )

        if send_result.get("success"):
            # Update proposal status to 'sent'
            db.update_proposal_status(proposal_id, 'sent')
            return {"message": f"Propuesta enviada a {client['email']}", "success": True}
        else:
            raise HTTPException(status_code=500, detail=send_result.get("error", "Error enviando email"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/{client_id}/proposals")
async def get_client_proposals(client_id: int):
    """Get all proposals for a client."""
    proposals = db.get_client_proposals(client_id)
    return {"proposals": proposals}


@app.delete("/api/proposals/{proposal_id}")
async def delete_proposal(proposal_id: int):
    """Delete a proposal."""
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    db.delete_proposal(proposal_id)
    return {"message": "Propuesta eliminada", "success": True}


@app.delete("/api/invoices/{invoice_id}")
async def delete_invoice(invoice_id: int):
    """Delete an invoice."""
    inv = db.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    db.delete_invoice(invoice_id)
    return {"message": "Factura eliminada", "success": True}


# Run with: python -m app.main
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
