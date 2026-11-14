import io
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, password_hash
from app.db import transaction, Record, add, change
from app.worker import tick
from conftest import ready, generated, approved, PROFILE, picture

def publish(c, detail, **overrides):
    body = {'candidate_ids': [r['id'] for r in detail['candidates']], 'demo': True, 'delivery_type': 'complete'} | overrides
    return c.post(f"/api/v1/consultations/{detail['id']}/deliveries", json=body, headers={'Idempotency-Key': 'publish'})

def test_complete_demo_workflow_and_readonly_session(client):
    detail = approved(client)
    assert detail['jobs'][0]['status'] == 'succeeded'
    r = publish(client, detail)
    assert r.status_code == 201, r.text
    delivery_id = r.json()['delivery_id']
    assert client.post(f'/api/v1/deliveries/{delivery_id}/presentation-session').status_code == 200
    assert client.get('/api/v1/consultations').status_code == 401
    presentation = client.get('/api/v1/presentation').json()
    assert len(presentation['candidates']) == 6 and presentation['demo']
    assert 'reviewed_by' not in str(presentation)
    assert 'dimensions' not in str(presentation)
    candidate_id = presentation['candidates'][0]['candidate_id']
    assert client.post('/api/v1/presentation/choice', json={'candidate_id': candidate_id}, headers={'X-Presentation-Action': 'choose'}).status_code == 200
    assert client.post('/api/v1/presentation/choice', json={'candidate_id': 'other'}, headers={'X-Presentation-Action': 'choose'}).status_code == 404
    assert client.post('/api/v1/presentation/exit', headers={'X-Presentation-Action': 'exit'}).status_code == 200
    assert client.get('/api/v1/presentation').status_code == 401

def test_auth_csrf_and_unapproved_publish(client):
    detail = generated(client)
    assert publish(client, detail).json()['error']['code'] == 'REVIEW_REQUIRED'
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/consultations', json={'customer_code': 'x'}).status_code == 403
    client.headers['X-CSRF-Token'] = token

def test_demo_cannot_publish_as_real_and_image_limit(client):
    detail = approved(client)
    assert publish(client, detail, demo=False).json()['error']['code'] == 'DEMO_DELIVERY_FORBIDDEN'
    assert publish(client, detail, candidate_ids=[str(n) for n in range(10)]).json()['error']['code'] == 'DELIVERY_IMAGE_LIMIT'
    assert publish(client, detail, candidate_ids=[detail['candidates'][0]['id']]).json()['error']['code'] == 'INSUFFICIENT_CANDIDATES'

def test_revision_update_invalidates_review_and_old_job(client):
    detail = approved(client)
    result = client.put(f"/api/v1/consultations/{detail['id']}/profile", json=PROFILE | {'expected_revision': detail['revision']})
    assert result.status_code == 200
    assert publish(client, detail).json()['error']['code'] == 'PROFILE_REVISION_CONFLICT'
    assert client.put(f"/api/v1/consultations/{detail['id']}/profile", json=PROFILE | {'expected_revision': detail['revision']}).status_code == 409
    fresh = client.get(f"/api/v1/consultations/{detail['id']}").json()
    assert all(r['stale'] for r in fresh['candidates'])

def test_generation_idempotency_and_content_conflict(client):
    c = ready(client)
    url = f"/api/v1/consultations/{c['id']}/generation-jobs"
    r = client.post(url, json={'profile_revision': c['revision']}, headers={'Idempotency-Key': 'same'})
    r2 = client.post(url, json={'profile_revision': c['revision']}, headers={'Idempotency-Key': 'same'})
    assert r.json() == r2.json()
    assert client.post(url, json={'profile_revision': c['revision']+1}, headers={'Idempotency-Key': 'same'}).status_code == 409
    # Queued job becomes obsolete before starting.
    client.put(f"/api/v1/consultations/{c['id']}/profile", json=PROFILE | {'expected_revision': c['revision']})
    tick()
    assert client.get('/api/v1/jobs/' + r.json()['job_id']).json()['status'] == 'cancelled'

def test_tenant_isolation(client):
    c = ready(client)
    with transaction() as db:
        add(db, 'user', 'another-salon', {'email': 'other@salon.local', 'password': password_hash('OtherSalon2026!'), 'name': 'other', 'role': 'stylist'})
    with TestClient(app) as other:
        response = other.post('/api/v1/auth/login', json={'email': 'other@salon.local', 'password': 'OtherSalon2026!'})
        other.headers['X-CSRF-Token'] = response.json()['csrf']
        assert other.get(f"/api/v1/consultations/{c['id']}").status_code == 404
        assert other.get('/api/v1/consultations').json() == []

def test_safe_upload_and_consent(client):
    c = client.post('/api/v1/consultations', json={'customer_code': 'x'}).json()
    url = f"/api/v1/consultations/{c['id']}/photos"
    assert client.post(url, data={'view': 'front'}, files={'file': ('x.jpg', picture())}).json()['error']['code'] == 'CONSENT_REQUIRED'
    client.post(f"/api/v1/consultations/{c['id']}/consents", json={'confirmed': True})
    assert client.post(url, data={'view': 'front'}, files={'file': ('x.jpg', b'not an image')}).status_code == 422
    assert client.post(url, data={'view': 'nonsense'}, files={'file': ('x.jpg', picture())}).status_code == 422

def test_deleted_assets_and_delivery_revocation(client):
    detail = approved(client)
    r = publish(client, detail)
    assert r.status_code == 201
    asset = detail['assets'][0]['id']
    assert client.get('/api/v1/assets/' + asset).status_code == 200
    assert client.delete('/api/v1/consultations/' + detail['id']).status_code == 200
    assert client.get('/api/v1/assets/' + asset).status_code == 404
    assert client.get('/api/v1/consultations/' + detail['id']).status_code == 404

def test_unknown_lengths_give_partial_not_fabricated_results(client):
    c = ready(client)
    client.put(f"/api/v1/consultations/{c['id']}/profile", json=PROFILE | {'expected_revision': c['revision'], 'lengths': {z:'unknown' for z in PROFILE['lengths']}})
    fresh = client.get(f"/api/v1/consultations/{c['id']}").json()
    client.post(f"/api/v1/consultations/{c['id']}/generation-jobs", json={'profile_revision': fresh['revision']}, headers={'Idempotency-Key': 'unknown'})
    tick()
    fresh = client.get(f"/api/v1/consultations/{c['id']}").json()
    assert fresh['jobs'][0]['status'] == 'partial'
    assert all(r['mode'] == 'grow_out' and r['growth']['month_min'] is None for r in fresh['candidates'])

def test_real_generation_requires_configuration(client, monkeypatch):
    c = ready(client)
    with transaction() as db: change(db.get(Record, c['id']), mode='real')
    monkeypatch.delenv('ARK_API_KEY', raising=False)
    r = client.post(f"/api/v1/consultations/{c['id']}/generation-jobs", json={'profile_revision': c['revision']}, headers={'Idempotency-Key': 'real'})
    assert r.status_code == 503 and r.json()['error']['code'] == 'MODEL_NOT_CONFIGURED'

def test_budget_reservation_is_atomic(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import app.main as main
    c = ready(client)
    with transaction() as db: change(db.get(Record, c['id']), mode='real', budget_cny=1, analysis={'blocking_issues': []})
    monkeypatch.setattr(main, 'configured', lambda: True)
    monkeypatch.setenv('IMAGE_ATTEMPT_PRICE_CNY', '1')
    monkeypatch.setenv('VISION_CALL_RESERVE_CNY', '1')
    def send(n):
        return client.post(f"/api/v1/consultations/{c['id']}/generation-jobs", json={'profile_revision': c['revision']}, headers={'Idempotency-Key': f'budget-{n}'})
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(send, [1,2]))
    assert all(r.json()['error']['code'] == 'BUDGET_EXCEEDED' for r in results)
    assert client.get(f"/api/v1/consultations/{c['id']}").json()['reserved_cny'] == 0

def test_revision_requires_review_and_keeps_history(client):
    detail = approved(client)
    old = detail['candidates'][0]
    url = f"/api/v1/candidates/{old['id']}/revision-jobs"
    r = client.post(url, json={'candidate_revision': 1, 'profile_revision': detail['revision'], 'adjustment': '整体更自然'}, headers={'Idempotency-Key': 'revise'})
    assert r.status_code == 202, r.text
    tick()
    fresh = client.get(f"/api/v1/consultations/{detail['id']}").json()
    assert len(fresh['candidates']) == 7
    assert next(r for r in fresh['candidates'] if r['id'] == old['id'])['stale']
    new = next(r for r in fresh['candidates'] if r['candidate_revision'] == 2)
    assert new['review'] == 'pending' and not new['stale']
    assert publish(client, detail).json()['error']['code'] == 'PROFILE_REVISION_CONFLICT'

def test_analysis_is_explicit_and_does_not_fill_preferences(client):
    c = ready(client)
    result = client.post(f"/api/v1/consultations/{c['id']}/analysis-jobs", json={}, headers={'Idempotency-Key': 'analyze'})
    assert result.status_code == 202
    tick()
    fresh = client.get(f"/api/v1/consultations/{c['id']}").json()
    assert fresh['analysis']['demo'] is True
    assert fresh['profile']['style_preferences'] == ['自然']

def test_concurrent_batch_reserves_once(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import app.main as main
    c = ready(client)
    with transaction() as db: change(db.get(Record, c['id']), mode='real', budget_cny=14, analysis={'blocking_issues': []})
    monkeypatch.setattr(main, 'configured', lambda: True)
    monkeypatch.setenv('IMAGE_ATTEMPT_PRICE_CNY', '1')
    monkeypatch.setenv('VISION_CALL_RESERVE_CNY', '1')
    def send(n):
        return client.post(f"/api/v1/consultations/{c['id']}/generation-jobs", json={'profile_revision': c['revision']}, headers={'Idempotency-Key': f'batch-{n}'})
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(send, [1,2]))
    assert sorted(r.status_code for r in results) == [202, 409]
    fresh = client.get(f"/api/v1/consultations/{c['id']}").json()
    assert fresh['reserved_cny'] == 14 and len(fresh['jobs']) == 1

def test_admin_account_and_actual_feedback(client):
    result = client.post('/api/v1/admin/users', json={'email':'stylist@salon.local','name':'发型师','password':'StylistDemo2026!'})
    assert result.status_code == 201
    detail = generated(client)
    response = client.post(f"/api/v1/consultations/{detail['id']}/feedback", json={'candidate_id': detail['candidates'][0]['id'], 'feasibility':'需调整','executed':False,'actual_deviation':'未执行'})
    assert response.status_code == 200
    metrics = client.get('/api/v1/admin/metrics').json()
    assert metrics['counts']['candidate'] == 6 and metrics['counts']['feedback'] == 1
    with TestClient(app) as stylist:
        r = stylist.post('/api/v1/auth/login', json={'email':'stylist@salon.local','password':'StylistDemo2026!'})
        stylist.headers['X-CSRF-Token'] = r.json()['csrf']
        assert stylist.get('/api/v1/admin/metrics').status_code == 403

def test_attempt_cap_and_regeneration_replaces_working_set(client):
    detail = generated(client)
    for i in range(2):
        result = client.post(f"/api/v1/consultations/{detail['id']}/generation-jobs", json={'profile_revision':detail['revision']}, headers={'Idempotency-Key':f'regen-{i}'})
        assert result.status_code == 202
        tick()
    fresh = client.get(f"/api/v1/consultations/{detail['id']}").json()
    assert fresh['attempts_used'] == 18
    assert len([r for r in fresh['candidates'] if not r['stale']]) == 6
    result = client.post(f"/api/v1/consultations/{detail['id']}/generation-jobs", json={'profile_revision':detail['revision']}, headers={'Idempotency-Key':'too-many'})
    assert result.json()['error']['code'] == 'BUDGET_EXCEEDED'

def test_real_generation_does_not_require_money_cap(client, monkeypatch):
    c = ready(client)
    monkeypatch.setenv('ARK_API_KEY', 'synthetic')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic')
    for name in ['IMAGE_ATTEMPT_PRICE_CNY', 'VISION_CALL_RESERVE_CNY', 'CONSULTATION_BUDGET_CNY']:
        monkeypatch.delenv(name, raising=False)
    with transaction() as db:
        change(db.get(Record, c['id']), mode='real', budget_cny=None, analysis={'blocking_issues':[]})
    response = client.post(f"/api/v1/consultations/{c['id']}/generation-jobs", json={'profile_revision':c['revision']}, headers={'Idempotency-Key':'no-money'})
    assert response.status_code == 202, response.text
    # No worker tick: this contract test must never call a real provider.
    with transaction() as db:
        job = db.get(Record, response.json()['job_id'])
        assert job.data['reserved_cny'] is None

def test_real_consultation_is_explicit_and_demo_history_kept(client, monkeypatch):
    monkeypatch.setenv('ARK_API_KEY', 'synthetic')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic')
    real = client.post('/api/v1/consultations', json={'customer_code':'真实测试','mode':'real'})
    demo = client.post('/api/v1/consultations', json={'customer_code':'演示测试','mode':'demo'})
    assert real.status_code == 201 and real.json()['mode'] == 'real'
    assert demo.status_code == 201 and demo.json()['mode'] == 'demo'
