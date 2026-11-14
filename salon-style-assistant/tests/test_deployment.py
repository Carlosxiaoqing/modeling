import pytest
import app.main as main

def test_public_origin_accepts_only_configured_site(client, monkeypatch):
    monkeypatch.setenv('PUBLIC_ORIGIN','https://studio.example.com')
    body={'email':'demo@salon.local','password':'SalonDemo2026!'}
    assert client.post('/api/v1/auth/login',json=body,headers={'Origin':'https://wrong.example'}).status_code == 403
    assert client.post('/api/v1/auth/login',json=body,headers={'Origin':'https://studio.example.com'}).status_code == 200

def test_origin_gate_cannot_be_bypassed(client, monkeypatch):
    monkeypatch.setenv('ORIGIN_ACCESS_TOKEN','synthetic-origin-token-0123456789abcdef')
    assert client.get('/api/v1/me').status_code == 403
    assert client.get('/api/v1/me',headers={'X-Origin-Token':'forged'}).status_code == 403
    assert client.get('/api/v1/me',headers={'X-Origin-Token':'synthetic-origin-token-0123456789abcdef'}).status_code == 200

def test_public_config_never_suggests_demo_login(client, monkeypatch):
    monkeypatch.setenv('PUBLIC_DEPLOYMENT','true')
    assert client.get('/api/v1/client-config').json() == {'demo_login_allowed':False}

def test_public_startup_refuses_existing_demo_account(client, monkeypatch):
    monkeypatch.setenv('PUBLIC_DEPLOYMENT','true')
    monkeypatch.setenv('PUBLIC_ORIGIN','https://studio.example.com')
    monkeypatch.setenv('ORIGIN_ACCESS_TOKEN','synthetic-origin-token-0123456789abcdef')
    monkeypatch.setattr(main,'SECURE',True)
    with pytest.raises(RuntimeError,match='演示账号'): main.init()
