"""SQLite-backed development accounts; deploy behind HTTPS for remote use."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import supabase_accounts
from pathlib import Path
from http.cookies import SimpleCookie

DATA = Path(os.environ.get('DATA_DIR', str(Path(__file__).resolve().parent / '.data')))
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
DB = DATA / 'accounts.sqlite3'
LOCK = threading.Lock()
ATTEMPTS = {}


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE, salt TEXT, password TEXT, data TEXT NOT NULL DEFAULT \'{"logs":[],"checkins":{}}\', revision INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER, expires REAL)')
    return db


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def user_for(handler, db):
    try:
        cookie = SimpleCookie(handler.headers.get('Cookie', ''))
        token = cookie['daily_session'].value
    except (KeyError, ValueError):
        return None
    return db.execute('SELECT users.id, users.email FROM users JOIN sessions ON users.id=sessions.user_id WHERE sessions.token=? AND sessions.expires>?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()


def reply(handler, status, body, cookie=None):
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    if cookie:
        handler.send_header('Set-Cookie', cookie)
    handler.end_headers()
    handler.wfile.write(json.dumps(body).encode())


def session_cookie(handler, token, age):
    secure = '; Secure' if handler.headers.get('X-Forwarded-Proto') == 'https' else ''
    return f'daily_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}{secure}'


def valid_data(data):
    if not isinstance(data, dict) or not isinstance(data.get('logs'), list) or not isinstance(data.get('checkins'), dict):
        return False
    if len(data['logs']) > 50000 or len(data['checkins']) > 10000:
        return False
    settings = data.get('settings', {})
    if not isinstance(settings, dict) or not isinstance(settings.get('calorieGoals', []), list):
        return False
    seen = set()
    for goal in settings.get('calorieGoals', []):
        if not isinstance(goal, dict) or not isinstance(goal.get('day'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', goal['day']) or type(goal.get('calories')) is not int or not 1 <= goal['calories'] <= 20000 or goal['day'] in seen:
            return False
        seen.add(goal['day'])
    for entry in data['logs']:
        if not isinstance(entry, dict) or entry.get('type') not in ('food', 'lift') or not isinstance(entry.get('name'), str) or not isinstance(entry.get('id'), str) or not isinstance(entry.get('day'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', entry['day']):
            return False
    return True


def handle(handler, path):
    if supabase_accounts.configured():
        return supabase_accounts.handle(handler, path, valid_data)
    if path not in ('/api/session', '/api/register', '/api/login', '/api/logout', '/api/data'):
        return False
    if handler.command == 'POST':
        origin = handler.headers.get('Origin')
        if origin and origin not in ('http://' + handler.headers.get('Host', ''), 'https://' + handler.headers.get('Host', '')):
            reply(handler, 403, {'error': 'Origin not allowed'})
            return True
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= 5_000_000:
                raise ValueError()
            body = json.loads(handler.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, TypeError):
            reply(handler, 400, {'error': 'Invalid request'})
            return True
    else:
        body = {}
    with connect() as db:
        user = user_for(handler, db)
        if path == '/api/session' and handler.command == 'GET':
            reply(handler, 200, {'email': user[1] if user else None})
        elif path in ('/api/register', '/api/login') and handler.command == 'POST':
            email, password = body.get('email', ''), body.get('password', '')
            if not isinstance(email, str) or not isinstance(password, str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()) or not 10 <= len(password) <= 128:
                reply(handler, 400, {'error': 'Enter a valid email and a password of 10–128 characters.'})
                return True
            email = email.strip().lower()
            ip = handler.client_address[0]
            with LOCK:
                recent = [t for t in ATTEMPTS.get(ip, []) if t > time.time()-900]
                ATTEMPTS[ip] = recent
                if len(recent) >= 15:
                    reply(handler, 429, {'error': 'Too many sign-in attempts. Try again in 15 minutes.'})
                    return True
                recent.append(time.time())
            if path == '/api/register':
                salt = secrets.token_hex(16)
                try:
                    cursor = db.execute('INSERT INTO users(email,salt,password) VALUES(?,?,?)', (email, salt, password_hash(password, salt)))
                    user_id = cursor.lastrowid
                except sqlite3.IntegrityError:
                    reply(handler, 409, {'error': 'Account already exists. Sign in instead.'})
                    return True
            else:
                row = db.execute('SELECT id,salt,password FROM users WHERE email=?', (email,)).fetchone()
                candidate = password_hash(password, row[1] if row else '00'*16)
                if not row or not hmac.compare_digest(candidate, row[2]):
                    reply(handler, 401, {'error': 'Email or password is incorrect.'})
                    return True
                user_id = row[0]
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time()+30*86400))
            db.commit()
            reply(handler, 200, {'email': email}, session_cookie(handler, token, 30*86400))
        elif path == '/api/logout' and handler.command == 'POST':
            cookie = SimpleCookie(handler.headers.get('Cookie', ''))
            if 'daily_session' in cookie:
                db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(cookie['daily_session'].value.encode()).hexdigest(),))
            db.commit()
            reply(handler, 200, {'ok': True}, session_cookie(handler, '', 0))
        elif path == '/api/data':
            if not user:
                reply(handler, 401, {'error': 'Sign in to sync your logs.'})
            elif handler.command == 'GET':
                row = db.execute('SELECT data,revision FROM users WHERE id=?', (user[0],)).fetchone()
                reply(handler, 200, {'data': json.loads(row[0]), 'revision': row[1]})
            elif handler.command == 'POST':
                data, revision = body.get('data'), body.get('revision')
                if not valid_data(data) or type(revision) is not int:
                    reply(handler, 400, {'error': 'Invalid log data'})
                    return True
                cursor = db.execute('UPDATE users SET data=?,revision=revision+1 WHERE id=? AND revision=?', (json.dumps(data, allow_nan=False), user[0], revision))
                db.commit()
                if cursor.rowcount:
                    reply(handler, 200, {'revision': revision+1})
                else:
                    reply(handler, 409, {'error': 'Your logs changed on another device. Refresh from account before trying again. Your unsaved form is still available.'})
            else:
                reply(handler, 405, {'error': 'Method not allowed'})
        else:
            reply(handler, 405, {'error': 'Method not allowed'})
    return True
