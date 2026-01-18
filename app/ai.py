# FILE: ai.py | PURPOSE: Claude AI integration for bilingual conversation handling

import os
import json
import re
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv
from . import database as db

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Initialize client lazily
_anthropic_client = None

def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client

SYSTEM_PROMPT = """Eres Paco, un asistente de negocios bilingüe para Jaime, dueño de una empresa de jardinería (landscaping) en el área de la Bahía de San Francisco.

## Tu rol:
- Hablas con Jaime SIEMPRE en español
- Cuando Jaime te pide comunicarte con un cliente, generas mensajes en inglés para ellos
- Aprendes y recuerdas las preferencias de cada cliente
- Rastreas servicios extra y precios
- Ayudas a generar facturas (invoices)

## Contexto del negocio:
- Jaime tiene 6 trabajadores: 3 para landscaping (proyectos) y 3 para mantenimiento
- Los clientes de mantenimiento pagan trimestralmente
- Servicios extras (podar árboles, reparar válvulas, etc.) se cobran aparte
- Jaime conoce a cada cliente personalmente y sabe cómo les gusta el trabajo

## Cómo funcionas:

1. **Cuando Jaime menciona un cliente:**
   - Si es nuevo, pregunta los datos básicos (nombre completo, teléfono, dirección)
   - Si existe, recuerda sus preferencias

2. **Cuando Jaime quiere cotizar algo o hacer una propuesta:**
   - Confirma el servicio y precio
   - Si Jaime dice "hazme una propuesta" o "manda cotización", crea la propuesta usando el formato [PROPUESTA]
   - Pregunta si quiere que le envíes la propuesta al cliente por email
   - Genera el mensaje en inglés profesional pero amigable

3. **Cuando Jaime te dice un precio:**
   - Lo guardas en tu libro de precios para referencia futura
   - La próxima vez que alguien pregunte por ese servicio, puedes sugerir el precio

4. **Cuando hay que facturar:**
   - Puedes generar facturas con el mantenimiento base + extras del trimestre

## Formato de respuesta:

Cuando Jaime te da información de un cliente nuevo, SIEMPRE registra al cliente:
```
[CLIENTE NUEVO]
Nombre: nombre completo
Teléfono: número (si lo tienes)
Dirección: dirección (si la tienes)
Notas: cualquier preferencia o nota
[FIN CLIENTE]
```

Cuando necesites enviar un mensaje a un cliente, usa este formato:
```
[MENSAJE PARA CLIENTE: nombre_del_cliente]
Contenido del mensaje en inglés aquí
[FIN MENSAJE]
```

Cuando registres un servicio/precio, usa:
```
[SERVICIO REGISTRADO]
Cliente: nombre
Servicio: descripción
Precio: $XX
[FIN SERVICIO]
```

Cuando hagas una cotización/propuesta, usa:
```
[PROPUESTA]
Cliente: nombre
Servicios:
- servicio 1: $precio
- servicio 2: $precio
Total: $total
Notas: cualquier nota adicional
[FIN PROPUESTA]
```

## Precios conocidos:
{price_book}

## Clientes actuales:
{clients}

## Historial de conversación reciente:
{recent_messages}

Responde siempre en español a Jaime. Sé conciso, práctico, y útil. Jaime es un hombre ocupado de 60+ años - no uses jerga técnica."""


def get_context():
    """Build context from database for the system prompt."""
    # Get price book
    prices = db.get_all_prices()
    if prices:
        price_book = "\n".join([f"- {p['service_type']}: ${p['default_price']}" for p in prices])
    else:
        price_book = "Todavía no hay precios registrados."

    # Get clients
    clients = db.get_all_clients()
    if clients:
        client_list = []
        for c in clients:
            prefs = json.loads(c['preferences']) if c['preferences'] else {}
            client_list.append(f"- {c['name']}: {c['address'] or 'sin dirección'}")
            if prefs:
                client_list.append(f"  Preferencias: {prefs}")
        clients_str = "\n".join(client_list)
    else:
        clients_str = "Todavía no hay clientes registrados."

    # Get recent messages
    messages = db.get_recent_messages(10)
    if messages:
        msg_list = [f"{'Jaime' if m['role'] == 'jaime' else 'Paco'}: {m['content'][:100]}..."
                   if len(m['content']) > 100 else f"{'Jaime' if m['role'] == 'jaime' else 'Jardín'}: {m['content']}"
                   for m in messages]
        recent_str = "\n".join(msg_list)
    else:
        recent_str = "Esta es una nueva conversación."

    return {
        'price_book': price_book,
        'clients': clients_str,
        'recent_messages': recent_str
    }


def process_response(response_text):
    """Extract structured data from AI response."""
    result = {
        'text': response_text,
        'client_messages': [],
        'services': [],
        'new_clients': [],
        'proposals': []
    }

    # Extract new clients
    client_pattern = r'\[CLIENTE NUEVO\]\s*Nombre:\s*(.+?)\s*(?:Teléfono:\s*(.+?)\s*)?(?:Dirección:\s*(.+?)\s*)?(?:Notas:\s*(.+?)\s*)?\[FIN CLIENTE\]'
    for match in re.finditer(client_pattern, response_text, re.DOTALL):
        result['new_clients'].append({
            'name': match.group(1).strip(),
            'phone': match.group(2).strip() if match.group(2) else None,
            'address': match.group(3).strip() if match.group(3) else None,
            'notes': match.group(4).strip() if match.group(4) else None
        })

    # Extract client messages
    client_msg_pattern = r'\[MENSAJE PARA CLIENTE: (.+?)\]\s*(.+?)\s*\[FIN MENSAJE\]'
    for match in re.finditer(client_msg_pattern, response_text, re.DOTALL):
        client_name = match.group(1).strip()
        message = match.group(2).strip()
        result['client_messages'].append({
            'client_name': client_name,
            'message': message
        })

    # Extract services
    service_pattern = r'\[SERVICIO REGISTRADO\]\s*Cliente: (.+?)\s*Servicio: (.+?)\s*Precio: \$?([\d.]+)\s*\[FIN SERVICIO\]'
    for match in re.finditer(service_pattern, response_text, re.DOTALL):
        result['services'].append({
            'client_name': match.group(1).strip(),
            'description': match.group(2).strip(),
            'price': float(match.group(3).strip())
        })

    # Extract proposals
    proposal_pattern = r'\[PROPUESTA\]\s*Cliente:\s*(.+?)\s*Servicios:\s*(.+?)\s*Total:\s*\$?([\d.]+)\s*(?:Notas:\s*(.+?)\s*)?\[FIN PROPUESTA\]'
    for match in re.finditer(proposal_pattern, response_text, re.DOTALL):
        # Parse services list
        services_text = match.group(2).strip()
        services = []
        for line in services_text.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                parts = line[1:].strip().split(':')
                if len(parts) >= 2:
                    svc_name = parts[0].strip()
                    price_match = re.search(r'\$?([\d.]+)', parts[1])
                    if price_match:
                        services.append({
                            'description': svc_name,
                            'price': float(price_match.group(1))
                        })

        result['proposals'].append({
            'client_name': match.group(1).strip(),
            'services': services,
            'total': float(match.group(3).strip()),
            'notes': match.group(4).strip() if match.group(4) else None
        })

    return result


def chat(user_message, session_id=None):
    """Process a message from Jaime and return response."""
    # Create or get session
    if not session_id:
        session_id = db.create_chat_session()

    # Save Jaime's message
    db.add_message('jaime', user_message, session_id=session_id)

    # Build context
    context = get_context()
    system = SYSTEM_PROMPT.format(**context)

    # Get messages for this session
    recent = db.get_session_messages(session_id, limit=20)
    messages = []
    for msg in recent:
        role = "user" if msg['role'] == 'jaime' else "assistant"
        messages.append({"role": role, "content": msg['content']})

    # Ensure we have the current message
    if not messages or messages[-1]['content'] != user_message:
        messages.append({"role": "user", "content": user_message})

    # Call Claude
    response = get_anthropic_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system,
        messages=messages
    )

    assistant_message = response.content[0].text

    # Save assistant response
    db.add_message('assistant', assistant_message)

    # Process structured data from response
    processed = process_response(assistant_message)
    processed['session_id'] = session_id

    # Handle new clients
    for nc in processed['new_clients']:
        existing = db.get_client_by_name(nc['name'])
        if not existing:
            client_id = db.create_client(
                name=nc['name'],
                phone=nc['phone'],
                address=nc['address'],
                notes=nc['notes']
            )
            processed['created_client_id'] = client_id

    # Handle client messages
    for cm in processed['client_messages']:
        found_client = db.get_client_by_name(cm['client_name'])
        if found_client:
            db.queue_client_message(found_client['id'], cm['message'])

    # Handle services
    for svc in processed['services']:
        found_client = db.get_client_by_name(svc['client_name'])
        if found_client:
            db.add_service(found_client['id'], svc['description'], svc['price'])
            db.set_price(svc['description'], svc['price'])

    # Handle proposals - save them for PDF generation
    for prop in processed['proposals']:
        found_client = db.get_client_by_name(prop['client_name'])
        if found_client:
            prop['client_id'] = found_client['id']
            # Save proposal to database
            proposal_id = db.create_proposal(
                client_id=found_client['id'],
                services=prop['services'],
                total=prop['total'],
                notes=prop.get('notes')
            )
            prop['proposal_id'] = proposal_id

    # Auto-name the chat session based on content
    session_title = generate_session_title(user_message, processed)
    if session_title:
        db.update_chat_session(session_id, title=session_title)

    return processed


def generate_session_title(user_message, processed):
    """Generate a descriptive title for the chat session based on content."""
    # Priority 1: New client created
    if processed.get('new_clients'):
        client_name = processed['new_clients'][0]['name']
        return f"Cliente: {client_name}"

    # Priority 2: Proposal created
    if processed.get('proposals'):
        client_name = processed['proposals'][0].get('client_name', '')
        if client_name:
            return f"Propuesta: {client_name}"

    # Priority 3: Client message generated
    if processed.get('client_messages'):
        client_name = processed['client_messages'][0].get('client_name', '')
        if client_name:
            return f"Mensaje: {client_name}"

    # Priority 4: Service registered
    if processed.get('services'):
        client_name = processed['services'][0].get('client_name', '')
        if client_name:
            return f"Servicio: {client_name}"

    # Priority 5: Try to extract client name from user message
    # Common patterns: "cliente [name]", "para [name]", "[name] quiere..."
    message_lower = user_message.lower()

    # Check if any existing client is mentioned
    clients = db.get_all_clients()
    for client in clients:
        if client['name'].lower() in message_lower:
            return f"Chat: {client['name']}"

    # Priority 6: Use first few words of the message (truncated)
    words = user_message.split()[:5]
    preview = ' '.join(words)
    if len(user_message) > len(preview):
        preview += '...'

    # Only update if it's more descriptive than default
    if preview and preview != 'Nueva conversacion':
        return preview

    return None


def get_suggested_price(service_description):
    """Get a suggested price for a service based on history."""
    price = db.get_price(service_description)
    return price['default_price'] if price else None
