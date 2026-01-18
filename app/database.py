# FILE: database.py | PURPOSE: SQLite database models and operations for Jardín

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DATABASE_PATH = Path(__file__).parent.parent / "data" / "jardin.db"

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Clients table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            language TEXT DEFAULT 'en',
            preferences TEXT,  -- JSON: how they like their work done
            maintenance_package TEXT,  -- JSON: what's included
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Services/extras table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            description TEXT NOT NULL,
            description_es TEXT,  -- Spanish description
            price REAL,
            service_date DATE,
            invoiced BOOLEAN DEFAULT FALSE,
            invoice_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    """)

    # Price book - learned pricing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_type TEXT NOT NULL UNIQUE,
            service_type_es TEXT,
            default_price REAL,
            notes TEXT,
            times_used INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Invoices table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            invoice_number TEXT UNIQUE,
            period_start DATE,
            period_end DATE,
            subtotal REAL,
            total REAL,
            status TEXT DEFAULT 'draft',  -- draft, sent, paid
            pdf_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    """)

    # Chat sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT 'Nueva conversacion',
            client_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    """)

    # Conversation memory - stores context for AI
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            role TEXT NOT NULL,  -- 'jaime' or 'assistant'
            content TEXT NOT NULL,
            metadata TEXT,  -- JSON: extracted info, client mentions, etc.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
        )
    """)

    # Add session_id column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE conversation_memory ADD COLUMN session_id INTEGER")
    except:
        pass

    # Messages to clients (outbox)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            direction TEXT NOT NULL,  -- 'outgoing' or 'incoming'
            channel TEXT DEFAULT 'sms',  -- 'sms', 'email', or 'both'
            content TEXT NOT NULL,
            subject TEXT,  -- for emails
            status TEXT DEFAULT 'pending',  -- pending, sent, delivered, failed
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    """)

    # Add contact_preference column to clients if it doesn't exist
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN contact_preference TEXT DEFAULT 'sms'")
    except:
        pass  # Column already exists

    # Add channel column to client_messages if it doesn't exist
    try:
        cursor.execute("ALTER TABLE client_messages ADD COLUMN channel TEXT DEFAULT 'sms'")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE client_messages ADD COLUMN subject TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE client_messages ADD COLUMN error_message TEXT")
    except:
        pass

    # Proposals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            proposal_number TEXT UNIQUE,
            services TEXT,  -- JSON array of services
            subtotal REAL,
            total REAL,
            notes TEXT,
            status TEXT DEFAULT 'draft',  -- draft, sent, accepted, declined
            pdf_path TEXT,
            valid_until DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    """)

    conn.commit()
    conn.close()


# Client operations
def get_all_clients():
    """Get all clients."""
    conn = get_connection()
    clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    conn.close()
    return [dict(c) for c in clients]


def get_client(client_id):
    """Get a specific client."""
    conn = get_connection()
    client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    return dict(client) if client else None


def get_client_by_name(name):
    """Find a client by name (case-insensitive partial match)."""
    conn = get_connection()
    client = conn.execute(
        "SELECT * FROM clients WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{name}%",)
    ).fetchone()
    conn.close()
    return dict(client) if client else None


def create_client(name, phone=None, email=None, address=None, language='en', preferences=None, maintenance_package=None, notes=None):
    """Create a new client."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO clients (name, phone, email, address, language, preferences, maintenance_package, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, phone, email, address, language,
          json.dumps(preferences) if preferences else None,
          json.dumps(maintenance_package) if maintenance_package else None,
          notes))
    client_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return client_id


def update_client(client_id, **kwargs):
    """Update client fields."""
    conn = get_connection()
    updates = []
    values = []
    for key, value in kwargs.items():
        if key in ['preferences', 'maintenance_package'] and value is not None:
            value = json.dumps(value)
        updates.append(f"{key} = ?")
        values.append(value)
    values.append(client_id)

    conn.execute(f"""
        UPDATE clients SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, values)
    conn.commit()
    conn.close()


# Service operations
def add_service(client_id, description, price, description_es=None, service_date=None, notes=None):
    """Add a service/extra for a client."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO services (client_id, description, description_es, price, service_date, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (client_id, description, description_es, price, service_date or datetime.now().date(), notes))
    service_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return service_id


def get_client_services(client_id, uninvoiced_only=False):
    """Get services for a client."""
    conn = get_connection()
    query = "SELECT * FROM services WHERE client_id = ?"
    if uninvoiced_only:
        query += " AND invoiced = FALSE"
    query += " ORDER BY service_date DESC"
    services = conn.execute(query, (client_id,)).fetchall()
    conn.close()
    return [dict(s) for s in services]


# Price book operations
def get_price(service_type):
    """Get price for a service type from the price book."""
    conn = get_connection()
    price = conn.execute(
        "SELECT * FROM price_book WHERE LOWER(service_type) LIKE LOWER(?)",
        (f"%{service_type}%",)
    ).fetchone()
    conn.close()
    return dict(price) if price else None


def set_price(service_type, price, service_type_es=None, notes=None):
    """Set or update a price in the price book."""
    conn = get_connection()
    existing = get_price(service_type)

    if existing:
        conn.execute("""
            UPDATE price_book
            SET default_price = ?, times_used = times_used + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (price, existing['id']))
    else:
        conn.execute("""
            INSERT INTO price_book (service_type, service_type_es, default_price, notes)
            VALUES (?, ?, ?, ?)
        """, (service_type, service_type_es, price, notes))

    conn.commit()
    conn.close()


def get_all_prices():
    """Get all prices from the price book."""
    conn = get_connection()
    prices = conn.execute("SELECT * FROM price_book ORDER BY service_type").fetchall()
    conn.close()
    return [dict(p) for p in prices]


# Chat sessions
def create_chat_session(title=None, client_id=None):
    """Create a new chat session."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_sessions (title, client_id)
        VALUES (?, ?)
    """, (title or 'Nueva conversacion', client_id))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_chat_sessions(limit=50):
    """Get all chat sessions with preview."""
    conn = get_connection()
    sessions = conn.execute("""
        SELECT cs.*, c.name as client_name,
               (SELECT content FROM conversation_memory
                WHERE session_id = cs.id ORDER BY created_at DESC LIMIT 1) as last_message
        FROM chat_sessions cs
        LEFT JOIN clients c ON cs.client_id = c.id
        ORDER BY cs.updated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(s) for s in sessions]


def get_chat_session(session_id):
    """Get a specific chat session."""
    conn = get_connection()
    session = conn.execute("""
        SELECT cs.*, c.name as client_name
        FROM chat_sessions cs
        LEFT JOIN clients c ON cs.client_id = c.id
        WHERE cs.id = ?
    """, (session_id,)).fetchone()
    conn.close()
    return dict(session) if session else None


def update_chat_session(session_id, title=None, client_id=None):
    """Update chat session title or client."""
    conn = get_connection()
    updates = ["updated_at = CURRENT_TIMESTAMP"]
    values = []
    if title:
        updates.append("title = ?")
        values.append(title)
    if client_id:
        updates.append("client_id = ?")
        values.append(client_id)
    values.append(session_id)
    conn.execute(f"UPDATE chat_sessions SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_or_create_default_session():
    """Get the most recent session or create one if none exists."""
    conn = get_connection()
    session = conn.execute("""
        SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT 1
    """).fetchone()
    conn.close()

    if session:
        return dict(session)['id']
    return create_chat_session()


# Conversation memory
def add_message(role, content, session_id=None, metadata=None):
    """Add a message to conversation history."""
    conn = get_connection()

    # If no session_id, use or create default
    if not session_id:
        session_id = get_or_create_default_session()

    conn.execute("""
        INSERT INTO conversation_memory (session_id, role, content, metadata)
        VALUES (?, ?, ?, ?)
    """, (session_id, role, content, json.dumps(metadata) if metadata else None))

    # Update session timestamp
    conn.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return session_id


def get_recent_messages(limit=20, session_id=None):
    """Get recent conversation messages, optionally for a specific session."""
    conn = get_connection()
    if session_id:
        messages = conn.execute("""
            SELECT * FROM conversation_memory
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (session_id, limit)).fetchall()
    else:
        messages = conn.execute("""
            SELECT * FROM conversation_memory
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(m) for m in reversed(messages)]


def get_session_messages(session_id, limit=100):
    """Get all messages for a specific session."""
    conn = get_connection()
    messages = conn.execute("""
        SELECT * FROM conversation_memory
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    """, (session_id, limit)).fetchall()
    conn.close()
    return [dict(m) for m in messages]


def delete_chat_session(session_id):
    """Delete a chat session and its messages."""
    conn = get_connection()
    conn.execute("DELETE FROM conversation_memory WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# Client messages (outbox)
def queue_client_message(client_id, content, direction='outgoing', channel='sms', subject=None):
    """Queue a message to send to a client."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO client_messages (client_id, content, direction, channel, subject)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, content, direction, channel, subject))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_pending_messages():
    """Get all pending outgoing messages."""
    conn = get_connection()
    messages = conn.execute("""
        SELECT cm.*, c.name as client_name, c.phone as client_phone, c.email as client_email,
               c.contact_preference
        FROM client_messages cm
        JOIN clients c ON cm.client_id = c.id
        WHERE cm.status = 'pending' AND cm.direction = 'outgoing'
        ORDER BY cm.created_at
    """).fetchall()
    conn.close()
    return [dict(m) for m in messages]


def get_message(message_id):
    """Get a specific message with client info."""
    conn = get_connection()
    message = conn.execute("""
        SELECT cm.*, c.name as client_name, c.phone as client_phone, c.email as client_email,
               c.contact_preference
        FROM client_messages cm
        JOIN clients c ON cm.client_id = c.id
        WHERE cm.id = ?
    """, (message_id,)).fetchone()
    conn.close()
    return dict(message) if message else None


def mark_message_sent(message_id):
    """Mark a message as sent."""
    conn = get_connection()
    conn.execute("""
        UPDATE client_messages SET status = 'sent', sent_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (message_id,))
    conn.commit()
    conn.close()


def mark_message_failed(message_id, error_message):
    """Mark a message as failed with error."""
    conn = get_connection()
    conn.execute("""
        UPDATE client_messages SET status = 'failed', error_message = ?
        WHERE id = ?
    """, (error_message, message_id))
    conn.commit()
    conn.close()


# Proposal operations
def generate_proposal_number():
    """Generate a unique proposal number."""
    now = datetime.now()
    prefix = f"PROP-{now.strftime('%Y%m')}"
    conn = get_connection()
    existing = conn.execute(
        "SELECT proposal_number FROM proposals WHERE proposal_number LIKE ?",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()
    next_num = len(existing) + 1
    return f"{prefix}-{next_num:03d}"


def create_proposal(client_id, services, total, notes=None, valid_days=30):
    """Create a new proposal."""
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()
    proposal_number = generate_proposal_number()
    valid_until = (datetime.now() + timedelta(days=valid_days)).date()

    cursor.execute("""
        INSERT INTO proposals (client_id, proposal_number, services, subtotal, total, notes, valid_until)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (client_id, proposal_number, json.dumps(services), total, total, notes, valid_until))
    proposal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return proposal_id


def get_proposal(proposal_id):
    """Get a specific proposal."""
    conn = get_connection()
    proposal = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    conn.close()
    if proposal:
        p = dict(proposal)
        p['services'] = json.loads(p['services']) if p['services'] else []
        return p
    return None


def get_proposal_by_number(proposal_number):
    """Get a proposal by its number."""
    conn = get_connection()
    proposal = conn.execute("SELECT * FROM proposals WHERE proposal_number = ?", (proposal_number,)).fetchone()
    conn.close()
    if proposal:
        p = dict(proposal)
        p['services'] = json.loads(p['services']) if p['services'] else []
        return p
    return None


def get_client_proposals(client_id):
    """Get all proposals for a client."""
    conn = get_connection()
    proposals = conn.execute("""
        SELECT * FROM proposals WHERE client_id = ? ORDER BY created_at DESC
    """, (client_id,)).fetchall()
    conn.close()
    result = []
    for p in proposals:
        prop = dict(p)
        prop['services'] = json.loads(prop['services']) if prop['services'] else []
        result.append(prop)
    return result


def get_all_proposals():
    """Get all proposals."""
    conn = get_connection()
    proposals = conn.execute("""
        SELECT p.*, c.name as client_name
        FROM proposals p
        JOIN clients c ON p.client_id = c.id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    result = []
    for p in proposals:
        prop = dict(p)
        prop['services'] = json.loads(prop['services']) if prop['services'] else []
        result.append(prop)
    return result


def update_proposal_pdf(proposal_id, pdf_path):
    """Update proposal with PDF path."""
    conn = get_connection()
    conn.execute("UPDATE proposals SET pdf_path = ? WHERE id = ?", (pdf_path, proposal_id))
    conn.commit()
    conn.close()


def update_proposal_status(proposal_id, status):
    """Update proposal status (draft, sent, accepted, declined)."""
    conn = get_connection()
    conn.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
    conn.commit()
    conn.close()


# Invoice operations
def get_all_invoices():
    """Get all invoices with client info."""
    conn = get_connection()
    invoices = conn.execute("""
        SELECT i.*, c.name as client_name, c.email as client_email
        FROM invoices i
        JOIN clients c ON i.client_id = c.id
        ORDER BY i.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(inv) for inv in invoices]


def get_invoice(invoice_id):
    """Get a specific invoice."""
    conn = get_connection()
    invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    conn.close()
    return dict(invoice) if invoice else None


def get_invoice_by_number(invoice_number):
    """Get invoice by number."""
    conn = get_connection()
    invoice = conn.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
    conn.close()
    return dict(invoice) if invoice else None


def update_invoice_status(invoice_id, status):
    """Update invoice status (draft, sent, paid)."""
    conn = get_connection()
    conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
    conn.commit()
    conn.close()


def delete_invoice(invoice_id):
    """Delete an invoice."""
    conn = get_connection()
    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()
    conn.close()


def delete_proposal(proposal_id):
    """Delete a proposal."""
    conn = get_connection()
    conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
    conn.commit()
    conn.close()


def delete_client(client_id):
    """Delete a client and all related data (services, messages, proposals, invoices)."""
    conn = get_connection()
    # Delete related data first (foreign key constraints)
    conn.execute("DELETE FROM services WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM client_messages WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM proposals WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM invoices WHERE client_id = ?", (client_id,))
    # Also clear chat sessions linked to this client
    conn.execute("UPDATE chat_sessions SET client_id = NULL WHERE client_id = ?", (client_id,))
    # Finally delete the client
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()


# Message history operations
def get_all_messages(limit=100):
    """Get all messages (sent and pending) with client info."""
    conn = get_connection()
    messages = conn.execute("""
        SELECT cm.*, c.name as client_name, c.phone as client_phone, c.email as client_email
        FROM client_messages cm
        JOIN clients c ON cm.client_id = c.id
        ORDER BY cm.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(m) for m in messages]


def get_client_messages(client_id, limit=50):
    """Get message history for a specific client."""
    conn = get_connection()
    messages = conn.execute("""
        SELECT * FROM client_messages
        WHERE client_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (client_id, limit)).fetchall()
    conn.close()
    return [dict(m) for m in messages]


# Initialize on import
init_db()
