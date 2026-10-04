"""Small localhost-demo authentication. Configuration is never cached or logged."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

COOKIE_NAME = 'effigov_staff'
SESSION_SECONDS = 8 * 60 * 60
RESIDENT_SECONDS = 60 * 60


class AuthConfigurationError(ValueError):
    """Missing or unsafe authentication configuration; fail closed."""


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8 or len(password) > 1024 or not password.strip():
        raise AuthConfigurationError('STAFF_PASSWORD must contain 8–1024 characters.')
    return password


def _secret(name: str) -> bytes:
    value = os.getenv(name, '')
    if len(value) < 32 or not value.strip():
        raise AuthConfigurationError(f'{name} must contain at least 32 characters.')
    return value.encode('utf-8')


def configured() -> bool:
    try:
        validate_password(os.getenv('STAFF_PASSWORD', ''))
        _secret('SESSION_SECRET')
        _secret('VOICE_WORKER_TOKEN')
        session_cookie_options()
        return True
    except AuthConfigurationError:
        return False


def session_cookie_options() -> dict:
    secure = os.getenv('SESSION_COOKIE_SECURE', 'false').strip().lower()
    if secure not in {'true', 'false', '1', '0'}:
        raise AuthConfigurationError('SESSION_COOKIE_SECURE must be true or false.')
    return dict(httponly=True, samesite='strict', path='/', secure=secure in {'true', '1'}, max_age=SESSION_SECONDS)


def _signature(body: str, key: bytes) -> str:
    return hmac.new(key, body.encode('ascii'), hashlib.sha256).hexdigest()


def sign_in(password: str, *, now: float | None = None) -> str | None:
    """Return a signed staff session or None for invalid credentials.

    Configuration errors raise so the caller can show an unavailable-service message,
    rather than reporting a bad password or accidentally opening the application.
    """
    configured_password = validate_password(os.getenv('STAFF_PASSWORD', ''))
    key = _secret('SESSION_SECRET')
    if not isinstance(password, str) or len(password) > 1024:
        return None
    expected = hashlib.sha256(configured_password.encode('utf-8')).digest()
    supplied = hashlib.sha256(password.encode('utf-8')).digest()
    if not hmac.compare_digest(expected, supplied):
        return None
    issued = int(time.time() if now is None else now)
    payload = dict(kind='staff', version=1, issued=issued, expires=issued + SESSION_SECONDS, nonce=secrets.token_urlsafe(16))
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()).decode().rstrip('=')
    return body + '.' + _signature(body, key)


def verify_staff(token: str | None, *, now: float | None = None) -> bool:
    try:
        # Removing the configured password also invalidates access, even if a signing
        # secret remains in the environment. Secret rotation invalidates old cookies.
        validate_password(os.getenv('STAFF_PASSWORD', ''))
        key = _secret('SESSION_SECRET')
        if not isinstance(token, str) or len(token) > 4096:
            return False
        body, separator, signature = token.partition('.')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_-]+', body) or not re.fullmatch(r'[a-f0-9]{64}', signature):
            return False
        if not hmac.compare_digest(signature, _signature(body, key)):
            return False
        raw = base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_', validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('kind') != 'staff' or payload.get('version') != 1:
            return False
        issued, expires = payload.get('issued'), payload.get('expires')
        if type(issued) is not int or type(expires) is not int or expires - issued != SESSION_SECONDS:
            return False
        current = time.time() if now is None else now
        return issued <= current < expires
    except (AuthConfigurationError, ValueError, TypeError, UnicodeError):
        return False


def verify_worker(authorization: str | None) -> bool:
    """Validate only the dedicated worker credential; grants no staff access itself.

    The middleware must additionally bind X-Call-ID to permitted route/query/body
    identifiers and the linked case. Never accept this token as a staff cookie.
    """
    try:
        expected = _secret('VOICE_WORKER_TOKEN')
        if not isinstance(authorization, str):
            return False
        scheme, separator, token = authorization.partition(' ')
        if not separator or scheme.lower() != 'bearer' or not token or token != token.strip():
            return False
        return hmac.compare_digest(token.encode('utf-8'), expected)
    except (AuthConfigurationError, UnicodeError):
        return False


def worker_call_id(value: str | None) -> str | None:
    """Accept only the canonical call UUID used by the backend, with no path syntax."""
    if not isinstance(value, str):
        return None
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None
    return parsed if value == parsed else None


def resident_token(call_id: str, *, now: float | None = None) -> str:
    """One-hour capability for a single public call, never a staff session."""
    if not worker_call_id(call_id):
        raise ValueError('Invalid call ID')
    issued = int(time.time() if now is None else now)
    payload = dict(kind='resident', call_id=call_id, issued=issued, expires=issued + RESIDENT_SECONDS)
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    return body + '.' + _signature(body, _secret('SESSION_SECRET'))


def verify_resident(authorization: str | None, call_id: str, *, now: float | None = None) -> bool:
    try:
        if not isinstance(authorization, str) or len(authorization) > 4096:
            return False
        scheme, _, token = authorization.partition(' ')
        body, _, signature = token.partition('.')
        if scheme.lower() != 'bearer' or not re.fullmatch(r'[A-Za-z0-9_-]+', body) or not re.fullmatch(r'[a-f0-9]{64}', signature):
            return False
        if not hmac.compare_digest(signature, _signature(body, _secret('SESSION_SECRET'))):
            return False
        payload = json.loads(base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_', validate=True))
        if not isinstance(payload, dict) or payload.get('kind') != 'resident' or payload.get('call_id') != call_id or not worker_call_id(call_id):
            return False
        issued, expires = payload.get('issued'), payload.get('expires')
        return (type(issued) is int and type(expires) is int and expires - issued == RESIDENT_SECONDS
                and issued <= (time.time() if now is None else now) < expires)
    except (AuthConfigurationError, ValueError, TypeError, UnicodeError):
        return False
