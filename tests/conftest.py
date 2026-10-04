import pytest

@pytest.fixture(autouse=True)
def demo_auth(monkeypatch):
    monkeypatch.setenv('STAFF_PASSWORD','test-staff-password')
    monkeypatch.setenv('SESSION_SECRET','s'*32)
    monkeypatch.setenv('VOICE_WORKER_TOKEN','w'*32)
    from backend import main
    main.login_failures.clear()
