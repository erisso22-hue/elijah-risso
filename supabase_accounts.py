"""Supabase Auth and per-user PostgREST storage. Uses only a publishable key.

Access/refresh tokens live in HttpOnly cookies; all database requests use the
signed-in user's access token so the SQL row-level policies remain enforced.
"""
import json
import os
import re
from http.cookies import SimpleCookie, CookieError
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROUTES = {'/api/session', '/api/register', '/api/login', '/api/logout', '/api/data'}
EMPTY = {'logs': [], 'checkins': {}, 'settings': {'calorieGoals': []}}


class ProviderError(Exception):
    def __init__(self, status, code=''):
        self.status, self.code = status, code


def configured():
    return bool(os.environ.get('SUPABASE_URL') or os.environ.get('SUPABASE_PUBLISHABLE_KEY'))


def configuration():
    base = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '').strip()
    url = urlsplit(base)
    if url.scheme != 'https' or not url.hostname or url.path or url.query or url.fragment or url.username or not key.startswith('sb_publishable_'):
        raise ProviderError(503, 'configuration')
    return base, key


def request(method, path, token=None, body=None, prefer=None):
    base, key = configuration()
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if prefer:
        headers['Prefer'] = prefer
    req = Request(base + path, method=method, headers=headers, data=json.dumps(body, allow_nan=False).encode() if body is not None else None)
    try:
        with urlopen(req, timeout=25) as response:
            data = response.read()
        return json.loads(data) if data else None
    except HTTPError as error:
        try:
            details = json.loads(error.read())
            code = details.get('error_code') or details.get('code', '')
        except (ValueError, AttributeError):
            code = ''
        raise ProviderError(error.code, code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ProviderError(503, 'unavailable') from None


def cookie(handler, name, value, age):
    secure = '; Secure' if handler.headers.get('X-Forwarded-Proto') == 'https' else ''
    return f'{name}={value}; HttpOnly; SameSite=Lax; Path=/; Max-Age={age}{secure}'


def session_cookies(handler, session):
    return [cookie(handler, 'ds_access', session['access_token'], int(session.get('expires_in', 3600))),
            cookie(handler, 'ds_refresh', session['refresh_token'], 30*86400)]


def clear_cookies(handler):
    return [cookie(handler, name, '', 0) for name in ('ds_access', 'ds_refresh', 'daily_session')]


def reply(handler, status, data, cookies=()):
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    for value in cookies:
        handler.send_header('Set-Cookie', value)
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def authenticate(handler):
    try:
        jar = SimpleCookie(handler.headers.get('Cookie', ''))
        access = jar['ds_access'].value if 'ds_access' in jar else None
        refresh = jar['ds_refresh'].value if 'ds_refresh' in jar else None
    except CookieError:
        return None, None, []
    if access:
        try:
            return request('GET', '/auth/v1/user', token=access), access, []
        except ProviderError as error:
            if error.status not in (401, 403):
                raise
    if refresh:
        try:
            session = request('POST', '/auth/v1/token?grant_type=refresh_token', body={'refresh_token': refresh})
            # Always obtain the user through Auth; never trust a decoded client JWT.
            user = request('GET', '/auth/v1/user', token=session['access_token'])
            return user, session['access_token'], session_cookies(handler, session)
        except ProviderError as error:
            if error.status not in (400, 401, 403):
                raise
    return None, None, clear_cookies(handler) if access or refresh else []


def load_row(user_id, token):
    query = urlencode({'user_id': 'eq.' + user_id, 'select': 'data,revision'})
    rows = request('GET', '/rest/v1/training_logs?' + query, token=token)
    if not rows:
        # Ignore a competing first insert; never replace existing account data.
        request('POST', '/rest/v1/training_logs?on_conflict=user_id', token=token,
                body={'user_id': user_id, 'data': EMPTY, 'revision': 0}, prefer='resolution=ignore-duplicates')
        rows = request('GET', '/rest/v1/training_logs?' + query, token=token)
    if not isinstance(rows, list) or len(rows) != 1:
        raise ProviderError(503, 'storage')
    return rows[0]


def handle(handler, path, valid_data):
    if path not in ROUTES:
        return False
    cookies = []
    try:
        configuration()  # Partial settings must not silently fall back to SQLite.
        if handler.command == 'POST':
            origin = handler.headers.get('Origin')
            host = handler.headers.get('Host', '')
            if origin and origin not in ('http://' + host, 'https://' + host):
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
        if path in ('/api/register', '/api/login') and handler.command == 'POST':
            email, password = body.get('email', ''), body.get('password', '')
            if not isinstance(email, str) or not isinstance(password, str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()) or not 10 <= len(password) <= 128:
                reply(handler, 400, {'error': 'Enter a valid email and a password of 10–128 characters.'})
                return True
            credentials = {'email': email.strip().lower(), 'password': password}
            endpoint = '/auth/v1/token?grant_type=password'
            if path == '/api/register':
                endpoint = '/auth/v1/signup'
                if handler.headers.get('Origin'):
                    endpoint += '?' + urlencode({'redirect_to': handler.headers['Origin']})
            result = request('POST', endpoint, body=credentials)
            if not result.get('access_token'):
                reply(handler, 200, {'email': None, 'confirmationRequired': True, 'message': 'Check your email for the confirmation link. After confirming, return here and sign in.'})
            else:
                cookies = session_cookies(handler, result)
                reply(handler, 200, {'email': result['user']['email'], 'storage': 'supabase'}, cookies)
            return True
        user, token, cookies = authenticate(handler)
        if path == '/api/session' and handler.command == 'GET':
            reply(handler, 200, {'email': user['email'] if user else None, 'storage': 'supabase'}, cookies)
        elif path == '/api/logout' and handler.command == 'POST':
            if token:
                request('POST', '/auth/v1/logout?scope=local', token=token, body={})
            reply(handler, 200, {'ok': True}, clear_cookies(handler))
        elif path == '/api/data':
            if not user:
                reply(handler, 401, {'error': 'Your session expired. Sign in again to sync your logs.'}, cookies)
            elif handler.command == 'GET':
                reply(handler, 200, load_row(user['id'], token), cookies)
            elif handler.command == 'POST':
                data, revision = body.get('data'), body.get('revision')
                if not valid_data(data) or type(revision) is not int or revision < 0:
                    reply(handler, 400, {'error': 'Invalid log data'}, cookies)
                    return True
                try:
                    json.dumps(data, allow_nan=False)
                except (ValueError, TypeError):
                    reply(handler, 400, {'error': 'Invalid numeric log data'}, cookies)
                    return True
                query = urlencode({'user_id': 'eq.'+user['id'], 'revision': 'eq.'+str(revision)})
                result = request('PATCH', '/rest/v1/training_logs?'+query, token=token,
                                 body={'data': data, 'revision': revision+1}, prefer='return=representation')
                if result:
                    reply(handler, 200, {'revision': result[0]['revision']}, cookies)
                else:
                    reply(handler, 409, {'error': 'Your logs changed on another device. Refresh from account before trying again. Your unsaved form is still available.'}, cookies)
            else:
                reply(handler, 405, {'error': 'Method not allowed'}, cookies)
        else:
            reply(handler, 405, {'error': 'Method not allowed'}, cookies)
    except ProviderError as error:
        if error.code == 'configuration':
            status, message = 503, 'Supabase setup is incomplete. Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in Render environment settings.'
        elif error.code == 'email_not_confirmed':
            status, message = 401, 'Confirm your email using the link from Supabase, then sign in again.'
        elif error.status == 429 or 'rate_limit' in error.code:
            status, message = 429, 'Too many requests. Wait a few minutes before trying again.'
        elif path in ('/api/login', '/api/register') and error.status in (400, 401, 422):
            status, message = 400, 'Could not sign in or create the account. Check your email/password and confirm your email if needed.'
        elif path == '/api/data' and error.code in ('42501', 'PGRST205', '42P01'):
            status, message = 503, 'Supabase log storage is not available yet. Check the training_logs table and its access policies.'
        else:
            status, message = 503, 'Could not reach Supabase or access this project. Your changes have not been saved. Check the project settings and try again.'
        reply(handler, status, {'error': message}, cookies)
    return True
