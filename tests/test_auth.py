"""Authentication tests are isolated from developer credentials and network services."""
import base64
import json

import pytest

from backend import auth


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv('STAFF_PASSWORD', 'fictional staff password')
    monkeypatch.setenv('SESSION_SECRET', 's' * 48)
    monkeypatch.setenv('VOICE_WORKER_TOKEN', 'w' * 48)
    monkeypatch.delenv('SESSION_COOKIE_SECURE', raising=False)


def test_password_session_tamper_expiry_and_cookie_settings():
    token = auth.sign_in('fictional staff password', now=1000)
    assert auth.verify_staff(token, now=1000)
    assert auth.verify_staff(token, now=1000 + auth.SESSION_SECONDS - 0.01)
    assert not auth.verify_staff(token, now=1000 + auth.SESSION_SECONDS)
    assert not auth.verify_staff(token, now=999)
    assert not auth.verify_staff(token[:-1] + ('0' if token[-1] != '0' else '1'), now=1000)
    assert not auth.verify_staff(None)
    assert auth.sign_in('wrong password', now=1000) is None
    assert auth.sign_in(None, now=1000) is None
    assert auth.session_cookie_options() == dict(httponly=True, samesite='strict', path='/', secure=False, max_age=auth.SESSION_SECONDS)


def test_cookie_payload_cannot_be_extended_by_browser():
    token = auth.sign_in('fictional staff password', now=1000)
    body, signature = token.split('.')
    payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    assert 'password' not in payload
    payload['expires'] += 1000000
    altered = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    assert not auth.verify_staff(altered + '.' + signature, now=1000)


@pytest.mark.parametrize('name', ['STAFF_PASSWORD', 'SESSION_SECRET', 'VOICE_WORKER_TOKEN'])
def test_missing_configuration_is_closed(monkeypatch, name):
    token = auth.sign_in('fictional staff password', now=1000)
    monkeypatch.delenv(name)
    assert not auth.configured()
    if name != 'VOICE_WORKER_TOKEN':
        assert not auth.verify_staff(token, now=1000)
        with pytest.raises(auth.AuthConfigurationError):
            auth.sign_in('fictional staff password', now=1000)
    else:
        assert not auth.verify_worker('Bearer ' + 'w' * 48)


def test_rotating_secret_invalidates_existing_cookie(monkeypatch):
    token = auth.sign_in('fictional staff password', now=1000)
    monkeypatch.setenv('SESSION_SECRET', 'different' * 8)
    assert not auth.verify_staff(token, now=1000)


def test_worker_credentials_do_not_authenticate_staff_or_accept_staff_cookie():
    staff = auth.sign_in('fictional staff password')
    assert auth.verify_worker('Bearer ' + 'w' * 48)
    assert auth.verify_worker('bearer ' + 'w' * 48)
    assert not auth.verify_worker('Bearer ' + staff)
    assert not auth.verify_worker('Bearer ' + 's' * 48)
    assert not auth.verify_worker('Bearer ' + 'w' * 47)
    assert not auth.verify_worker('Bearer ' + 'w' * 48 + ' ')
    assert not auth.verify_worker('Basic ' + 'w' * 48)
    assert not auth.verify_worker(None)
    assert not auth.verify_staff('w' * 48)


def test_canonical_worker_call_id_only():
    identity = '2fd2f407-2cbe-4b96-ae35-57d89d4211e1'
    assert auth.worker_call_id(identity) == identity
    for invalid in [None, '', '../calls/all', identity + '/finish', identity.upper(), identity.replace('-', '')]:
        assert auth.worker_call_id(invalid) is None


@pytest.mark.parametrize('token', ['', 'garbage', 'aaa.bbb.ccc', '☃.abc', 'a' * 5000])
def test_malformed_cookie_does_not_raise(token):
    assert not auth.verify_staff(token)


def test_configuration_is_reloaded_and_unicode_passwords_work(monkeypatch):
    assert auth.configured()
    monkeypatch.setenv('STAFF_PASSWORD', 'contraseña de prueba')
    assert auth.sign_in('fictional staff password') is None
    token = auth.sign_in('contraseña de prueba')
    assert auth.verify_staff(token)
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'true')
    assert auth.session_cookie_options()['secure'] is True
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'perhaps')
    assert not auth.configured()


@pytest.mark.parametrize('name,value', [('STAFF_PASSWORD', 'short'), ('SESSION_SECRET', 'short'), ('VOICE_WORKER_TOKEN', 'short')])
def test_weak_configuration_is_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert not auth.configured()
