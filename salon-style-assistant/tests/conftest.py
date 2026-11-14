import os
import tempfile
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="salon-tests-")
os.environ["MODEL_MODE"] = "demo"
os.environ["EMBEDDED_WORKER"] = "false"
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.db import Base, engine
from app.main import app, RATE

@pytest.fixture(autouse=True)
def reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    RATE.clear()

@pytest.fixture
def client():
    with TestClient(app) as c:
        response = c.post('/api/v1/auth/login', json={"email": "demo@salon.local", "password": "SalonDemo2026!"})
        assert response.status_code == 200
        c.headers['X-CSRF-Token'] = response.json()['csrf']
        yield c

def picture():
    image = Image.new('RGB', (400, 500), '#aabbaa')
    out = io.BytesIO()
    image.save(out, 'JPEG')
    return out.getvalue()

PROFILE = {"expected_revision": 1, "modes": ["current", "grow_out"], "lengths": {z: "12-20" for z in ['fringe', 'top', 'sides', 'back']}, "style_preferences": ['自然'], "cut_tolerance": '可明显改变', "fringe_preference": '可改变', "tie_back_need": '不需要', "daily_styling_time": '5～15 分钟', "perm_acceptance": '不接受', "waiting_horizon": '不限制', "curl_pattern": '直', "strand_thickness": '中等', "density": '中等', "photo_hair_state": '干发', "treatment_history": ['无'], "damage_observation": '无明显问题'}

def ready(c):
    r = c.post('/api/v1/consultations', json={"customer_code": '测试顾客'})
    assert r.status_code == 201
    id = r.json()['id']
    c.post(f'/api/v1/consultations/{id}/consents', json={"confirmed": True})
    for view in ['front', 'left']:
        assert c.post(f'/api/v1/consultations/{id}/photos', data={'view': view}, files={'file': ('image.jpg', picture(), 'image/jpeg')}).status_code == 201
    revision = c.get(f'/api/v1/consultations/{id}').json()['revision']
    r = c.put(f'/api/v1/consultations/{id}/profile', json=PROFILE | {'expected_revision': revision})
    assert r.status_code == 200, r.text
    return r.json()

def generated(c):
    from app.worker import tick
    consultation = ready(c)
    r = c.post(f"/api/v1/consultations/{consultation['id']}/generation-jobs", json={'profile_revision': consultation['revision']}, headers={'Idempotency-Key': 'generation-1'})
    assert r.status_code == 202, r.text
    tick()
    detail = c.get(f"/api/v1/consultations/{consultation['id']}").json()
    assert len(detail['candidates']) == 6, detail
    return detail

def approved(c):
    detail = generated(c)
    for candidate in detail['candidates']:
        r = c.post(f"/api/v1/candidates/{candidate['id']}/reviews", json={'candidate_revision': 1, 'profile_revision': detail['revision'], 'decision': 'approved', 'viewed': True})
        assert r.status_code == 200, r.text
    return detail
