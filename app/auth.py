# FILE: auth.py | PURPOSE: Simple authentication for Jaime and Erika

import os
import bcrypt
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import secrets

from .database import get_connection

# Session storage (in-memory for simplicity, could move to DB)
sessions = {}

SESSION_DURATION_HOURS = 24 * 7  # 1 week


def init_users_table():
    """Create users table if not exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def create_user(name: str, username: str, password: str) -> int:
    """Create a new user with hashed password."""
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, username, password_hash)
            VALUES (?, ?, ?)
        """, (name, username, password_hash))
        user_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Username '{username}' already exists")
    conn.close()
    return user_id


def verify_password(username: str, password: str) -> Optional[dict]:
    """Verify username/password and return user if valid."""
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not user:
        return None

    user_dict = dict(user)
    if bcrypt.checkpw(password.encode(), user_dict['password_hash'].encode()):
        # Update last login
        conn = get_connection()
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user_dict['id'],)
        )
        conn.commit()
        conn.close()
        return user_dict

    return None


def create_session(user_id: int) -> str:
    """Create a session token for a user."""
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "user_id": user_id,
        "expires": datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)
    }
    return token


def get_session_user(token: str) -> Optional[dict]:
    """Get user from session token if valid."""
    if not token or token not in sessions:
        return None

    session = sessions[token]
    if datetime.now() > session["expires"]:
        del sessions[token]
        return None

    conn = get_connection()
    user = conn.execute(
        "SELECT id, name, username FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()

    return dict(user) if user else None


def logout(token: str):
    """Remove a session."""
    if token in sessions:
        del sessions[token]


def get_all_users():
    """Get all users (without password hashes)."""
    conn = get_connection()
    users = conn.execute(
        "SELECT id, name, username, created_at, last_login FROM users"
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]


def user_exists(username: str) -> bool:
    """Check if a username exists."""
    conn = get_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return user is not None


def setup_default_users():
    """Create Jaime and Erika accounts if they don't exist."""
    init_users_table()

    # Default passwords
    defaults = [
        ("Jaime", "jaime", "jaime123"),
        ("Erika", "erika", "erika123"),
        ("David", "david", "david123"),
    ]

    created = []
    for name, username, password in defaults:
        if not user_exists(username):
            create_user(name, username, password)
            created.append(username)

    return created


# Initialize on import
init_users_table()
