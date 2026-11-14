import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Request, Response, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import Base, engine, transaction, Record, add, change, DATA, ROOT, uid, now
from .rules import LENGTHS, ZONES, feasibility
from .providers import configured, configured_price, image_model, ProviderFailure
from .worker import loop

MODEL_MODE = os.getenv("MODEL_MODE", "demo")
SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_TTL = 8 * 3600
RATE = {}

def fail(code, message, status=422):
    raise BusinessError(code, message, status)

class BusinessError(Exception):
    def __init__(self, code, message, status): self.code, self.message, self.status = code, message, status

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()

def password_verify(password, digest):
    return hmac.compare_digest(password_hash(password, digest.split(":")[0]), digest)

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

def init():
    Base.metadata.create_all(engine)
    if os.getenv("PUBLIC_DEPLOYMENT") == "true":
        if not SECURE or not os.getenv("PUBLIC_ORIGIN", "").startswith("https://") or len(os.getenv("ORIGIN_ACCESS_TOKEN", "")) < 32:
            raise RuntimeError("公开部署需要安全 Cookie、PUBLIC_ORIGIN 和至少 32 字符 ORIGIN_ACCESS_TOKEN")
    with transaction() as db:
        if not db.scalars(select(Record).where(Record.kind == "user")).first():
            local_demo = MODEL_MODE == "demo" and os.getenv("PUBLIC_DEPLOYMENT") != "true"
            identity = os.getenv("ADMIN_EMAIL", "demo@salon.local" if local_demo else "")
            password = os.getenv("ADMIN_PASSWORD", "SalonDemo2026!" if local_demo else "")
            if not identity or len(password) < 12: raise RuntimeError("真实模式需要 ADMIN_EMAIL 和至少 12 位 ADMIN_PASSWORD")
            if os.getenv("PUBLIC_DEPLOYMENT") == "true" and (identity == "demo@salon.local" or password == "SalonDemo2026!"):
                raise RuntimeError("公开部署不能使用默认演示账号")
            salon = add(db, "salon", "bootstrap", {"name": "青禾 SALON · 体验门店"})
            salon.salon_id = salon.id
            add(db, "user", salon.id, {"email": identity, "password": password_hash(password), "name": "体验发型师", "role": "admin"})
        if os.getenv("PUBLIC_DEPLOYMENT") == "true":
            for u in db.scalars(select(Record).where(Record.kind == "user")):
                if u.data["email"] == "demo@salon.local" or password_verify("SalonDemo2026!", u.data["password"]):
                    raise RuntimeError("数据库仍含默认演示账号，请使用独立部署数据库")

@asynccontextmanager
async def lifespan(app):
    init()
    stop = threading.Event()
    thread = None
    if os.getenv("EMBEDDED_WORKER", "true") == "true":
        thread = threading.Thread(target=loop, args=(stop,), daemon=True)
        thread.start()
    yield
    stop.set()
    if thread: thread.join(timeout=2)

app = FastAPI(title="青禾 · 沙龙发型设计助手", lifespan=lifespan)

@app.exception_handler(BusinessError)
async def business_handler(request, exc):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, "retryable": False, "request_id": uid()}}, status_code=exc.status)

@app.middleware("http")
async def security_headers(request, call_next):
    origin_secret = os.getenv("ORIGIN_ACCESS_TOKEN")
    if origin_secret and not hmac.compare_digest(request.headers.get("X-Origin-Token", ""), origin_secret):
        return JSONResponse({"error":{"code":"ORIGIN_FORBIDDEN","message":"请通过网页入口访问。","retryable":False}}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    return response

def auth(request: Request):
    raw = request.cookies.get("salon_session", "")
    with transaction() as db:
        session = db.get(Record, token_hash(raw)) if raw else None
        if not session or session.kind != "session" or session.data["expires"] < time.time():
            fail("UNAUTHENTICATED", "请先登录", 401)
        user = db.get(Record, session.parent_id)
        if not user: fail("UNAUTHENTICATED", "账号不可用", 401)
        if request.method not in ["GET", "HEAD", "OPTIONS"]:
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.data["csrf"]):
                fail("CSRF_INVALID", "会话校验失败，请重新登录", 403)
        return {"id": user.id, "salon_id": user.salon_id, **user.data, "session_id": session.id, "csrf": session.data["csrf"]}

def get(db, id, user, kind=None):
    r = db.get(Record, id, with_for_update=True)
    if not r or r.salon_id != user["salon_id"] or (kind and r.kind != kind): fail("NOT_FOUND", "资源不存在", 404)
    if r.data.get("deleted"): fail("ASSET_DELETED", "咨询已删除", 404)
    return r

def public(r): return {"id": r.id, "revision": r.revision, "created_at": r.created_at, **r.data}
def audit(db, user, action, resource): add(db, "audit", user["salon_id"], {"actor": user["id"], "action": action, "resource": resource, "timestamp": now()})

def reserve_money(c, image_calls=0, vision_calls=0):
    """Optional operator cap. Missing pricing is unknown, never a zero-cost claim."""
    if c.data["mode"] != "real": return 0
    if not configured(): fail("MODEL_NOT_CONFIGURED", "请配置两家模型 API 密钥", 503)
    try:
        image_price = configured_price("IMAGE_ATTEMPT_PRICE_CNY") if image_calls else 0
        vision_price = configured_price("VISION_CALL_RESERVE_CNY") if vision_calls else 0
    except ProviderFailure: fail("BUDGET_CONFIG_INVALID", "选填的价格配置无效，请管理员检查")
    reservation = None if image_price is None or vision_price is None else image_price*image_calls + vision_price*vision_calls
    cap = c.data.get("budget_cny")
    if cap and (reservation is None or c.data["reserved_cny"]+reservation > cap):
        fail("BUDGET_EXCEEDED", "已设置的金额上限无法满足本次调用；请管理员检查价格或上限")
    change(c, reserved_cny=c.data["reserved_cny"]+(reservation or 0))
    return reservation

def idempotent(db, request, user, operation, parent, body):
    key = request.headers.get("Idempotency-Key")
    if not key or len(key) > 120: fail("IDEMPOTENCY_REQUIRED", "请提供有效的幂等键")
    id = hashlib.sha256(f"{user['salon_id']}:{parent}:{operation}:{key}".encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    existing = db.get(Record, id, with_for_update=True)
    if existing:
        if existing.data["fingerprint"] != fingerprint: fail("IDEMPOTENCY_CONFLICT", "同一幂等键对应的内容不同", 409)
        return existing, existing.data["result"]
    return add(db, "idempotency", user["salon_id"], {"fingerprint": fingerprint}, parent, id), None

class Login(BaseModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=200)

@app.post("/api/v1/auth/login")
def login(body: Login, request: Request, response: Response):
    origin = request.headers.get("origin")
    expected_origin = os.getenv("PUBLIC_ORIGIN", str(request.base_url).rstrip("/"))
    if origin and origin != expected_origin: fail("CSRF_INVALID", "请从本站登录", 403)
    ip = request.client.host if request.client else "local"
    attempts = [t for t in RATE.get(ip, []) if t > time.time()-60]
    if len(attempts) >= 10: fail("RATE_LIMITED", "请求过多，请稍后重试", 429)
    RATE[ip] = attempts + [time.time()]
    with transaction() as db:
        users = db.scalars(select(Record).where(Record.kind == "user")).all()
        user = next((u for u in users if u.data["email"] == body.email), None)
        if not user or not password_verify(body.password, user.data["password"]): fail("LOGIN_FAILED", "账号或密码不正确", 401)
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        add(db, "session", user.salon_id, {"expires": time.time()+SESSION_TTL, "csrf": csrf}, user.id, token_hash(raw))
        response.set_cookie("salon_session", raw, httponly=True, secure=SECURE, samesite="strict", max_age=SESSION_TTL)
        return {"name": user.data["name"], "csrf": csrf}

@app.get("/api/v1/me")
def me(user=Depends(auth)):
    return {k: user[k] for k in ["id", "name", "role", "csrf"]} | {"mode": MODEL_MODE, "real_configured": configured(), "image_model": image_model(), "salon_name": "青禾 SALON", "retention_days": 30}

@app.post("/api/v1/auth/logout")
def logout(response: Response, user=Depends(auth)):
    with transaction() as db: db.delete(db.get(Record, user["session_id"]))
    response.delete_cookie("salon_session")
    return {"ok": True}

class CreateConsultation(BaseModel):
    customer_code: str = Field(min_length=1, max_length=40)
    mode: Literal["real", "demo"] | None = None

@app.post("/api/v1/consultations", status_code=201)
def create(body: CreateConsultation, user=Depends(auth)):
    mode = body.mode or MODEL_MODE
    if mode == "real" and not configured(): fail("MODEL_NOT_CONFIGURED", "真实模式需要配置模型密钥", 503)
    with transaction() as db:
        cap = os.getenv("CONSULTATION_BUDGET_CNY")
        c = add(db, "consultation", user["salon_id"], {"customer_code": body.customer_code, "status": "collecting", "mode": mode, "consent": False, "profile": None, "attempts_used": 0, "reserved_cny": 0, "budget_cny": float(cap) if cap else None, "stylist_id": user["id"]})
        audit(db, user, "consultation_created", c.id)
        return public(c)

@app.get("/api/v1/consultations")
def listing(user=Depends(auth)):
    with transaction() as db:
        return [public(r) for r in db.scalars(select(Record).where(Record.kind == "consultation", Record.salon_id == user["salon_id"]).order_by(Record.created_at.desc())) if not r.data.get("deleted")]

@app.get("/api/v1/consultations/{id}")
def detail(id: str, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        related = db.scalars(select(Record).where(Record.parent_id == id)).all()
        assets = [{"id": r.id, "view": r.data["view"], "kind": r.data["kind"]} for r in related if r.kind == "asset"]
        candidates = [public(r) | {"stale": r.data["profile_revision"] != c.revision or r.data.get("superseded", False)} for r in related if r.kind == "candidate"]
        candidates.sort(key=lambda r: (r["mode"], -(r["score"] or 0), r["created_at"]))
        for mode in ["current", "grow_out"]:
            for rank, candidate in enumerate([r for r in candidates if r["mode"] == mode and not r["stale"]], 1): candidate["system_rank"] = rank
        return public(c) | {"assets": assets, "candidates": candidates, "jobs": [public(r) for r in related if r.kind == "job"], "deliveries": [public(r) for r in related if r.kind == "delivery"]}

class Consent(BaseModel):
    confirmed: bool
    text_version: Literal["v1"] = "v1"

@app.post("/api/v1/consultations/{id}/consents")
def consent(id: str, body: Consent, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        change(c, consent=body.confirmed)
        add(db, "consent", c.salon_id, {**body.model_dump(), "purpose": "本次发型设计", "providers": ["Qwen", "Seedream"], "operator": user["id"], "confirmed_at": now()}, id)
        if not body.confirmed:
            c.revision += 1
            for r in db.scalars(select(Record).where(Record.parent_id == id, Record.kind == "delivery")): change(r, revoked=True)
        return {"ok": True}

@app.post("/api/v1/consultations/{id}/photos", status_code=201)
async def upload(id: str, view: str = Form(...), file: UploadFile = File(...), user=Depends(auth)):
    if view not in ["front", "left", "right", "back", "top"]: fail("INVALID_VIEW", "照片角度无效")
    with transaction() as db:
        c = get(db, id, user, "consultation")
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "请先确认照片使用授权")
    data = await file.read(15*1024*1024+1)
    if len(data) > 15*1024*1024: fail("PHOTO_TOO_LARGE", "照片不能超过 15 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in ["JPEG", "PNG", "WEBP"]: fail("PHOTO_FORMAT", "请使用 JPEG、PNG 或 WebP；HEIC 请先转换为 JPEG")
                if original.width*original.height > 40_000_000: fail("PHOTO_TOO_LARGE", "照片不能超过 40 MP")
                if min(original.size) < 160: fail("PHOTO_QUALITY_BLOCKED", "照片过小，请重新拍摄")
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((2048, 2048))
                asset_id = uid()
                folder = DATA / "assets"
                folder.mkdir(exist_ok=True)
                path = folder / f"{asset_id}.jpg"
                image.save(path, "JPEG", quality=90, exif=b"")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning): fail("PHOTO_FORMAT", "照片无法安全解码，请换一张")
    with transaction() as db:
        c = get(db, id, user, "consultation")
        if not c.data["consent"]:
            path.unlink(missing_ok=True)
            fail("CONSENT_REQUIRED", "授权已撤回")
        existing = db.scalars(select(Record).where(Record.kind == "asset", Record.parent_id == id)).all()
        for r in existing:
            if r.data["kind"] == "original" and r.data["view"] == view:
                Path(r.data["path"]).unlink(missing_ok=True)
                db.delete(r)
        asset = add(db, "asset", c.salon_id, {"path": str(path), "kind": "original", "view": view, "width": image.width, "height": image.height, "hash": hashlib.sha256(path.read_bytes()).hexdigest()}, id, asset_id)
        c.revision += 1
        change(c, status="collecting", analysis=None)
        audit(db, user, "photo_uploaded", id)
        return {"id": asset.id, "view": view}

@app.get("/api/v1/assets/{id}")
def asset(id: str, user=Depends(auth)):
    with transaction() as db:
        a = get(db, id, user, "asset")
        c = get(db, a.parent_id, user, "consultation")
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "授权已撤回", 403)
        return FileResponse(a.data["path"], media_type="image/jpeg")

class Profile(BaseModel):
    expected_revision: int
    modes: list[Literal["current", "grow_out"]] = Field(min_length=1, max_length=2)
    lengths: dict[str, str]
    style_preferences: list[Literal["自然", "利落", "柔和", "成熟", "时尚", "个性"]] = Field(max_length=3)
    cut_tolerance: Literal["仅修整", "适度剪短", "可明显改变"]
    fringe_preference: Literal["保留", "可改变", "不要刘海", "无偏好"]
    tie_back_need: Literal["必须", "偶尔", "不需要"]
    daily_styling_time: Literal["基本不打理", "5 分钟内", "5～15 分钟", "更久"]
    perm_acceptance: Literal["不接受", "可讨论", "接受"]
    waiting_horizon: Literal["3 个月内", "半年内", "一年内", "不限制"]
    curl_pattern: Literal["直", "微卷", "明显卷", "不确定"]
    strand_thickness: Literal["细软", "中等", "粗硬", "不确定"]
    density: Literal["偏少", "中等", "偏多", "不确定"]
    photo_hair_state: Literal["干发", "湿发", "较多造型产品"]
    treatment_history: list[Literal["无", "烫过", "染过", "漂过", "不确定"]] = Field(min_length=1, max_length=3)
    damage_observation: Literal["无明显问题", "有受损表现", "需判断"]

    @model_validator(mode="after")
    def lengths_valid(self):
        if set(self.lengths) != set(ZONES) or any(v not in LENGTHS for v in self.lengths.values()): raise ValueError("请完整选择四个区域的有效长度档位")
        self.modes = list(dict.fromkeys(self.modes))
        return self

@app.put("/api/v1/consultations/{id}/profile")
def profile(id: str, body: Profile, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        if body.expected_revision != c.revision: fail("PROFILE_REVISION_CONFLICT", "条件已更新，请刷新", 409)
        data = body.model_dump(exclude={"expected_revision"})
        c.revision += 1
        change(c, profile=data, status="ready", confirmed_by=user["id"], confirmed_at=now())
        add(db, "profile_revision", c.salon_id, {"fields": data, "revision": c.revision, "source": "stylist", "confirmed_by": user["id"], "confirmed_at": now()}, id)
        return public(c)

class Generation(BaseModel):
    profile_revision: int

@app.post("/api/v1/consultations/{id}/analysis-jobs", status_code=202)
def analyze(id: str, request: Request, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        record, previous = idempotent(db, request, user, "analysis", id, {"revision": c.revision})
        if previous: return previous
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "请先确认照片使用授权")
        assets = db.scalars(select(Record).where(Record.kind == "asset", Record.parent_id == id)).all()
        views = {r.data["view"] for r in assets if r.data["kind"] == "original"}
        if "front" not in views or not views.intersection({"left", "right"}): fail("PHOTO_QUALITY_BLOCKED", "请补充正面与侧面照片")
        for running in db.scalars(select(Record).where(Record.kind == "job", Record.parent_id == id)):
            if running.data["status"] in ["queued", "running"]: fail("JOB_ACTIVE", "已有任务运行中", 409)
        reservation = reserve_money(c, vision_calls=1)
        j = add(db, "job", c.salon_id, {"type": "analysis", "profile_revision": c.revision, "modes": [], "status": "queued", "stage": "等待照片分析", "completed": 0, "target": 1, "reserved_cny": reservation, "heartbeat": time.time()}, id)
        change(record, result={"job_id": j.id, "status": "queued"})
        return record.data["result"]

@app.post("/api/v1/consultations/{id}/generation-jobs", status_code=202)
def generate(id: str, body: Generation, request: Request, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        record, previous = idempotent(db, request, user, "generate", id, body.model_dump())
        if previous: return previous
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "请先确认照片使用授权")
        if c.revision != body.profile_revision: fail("PROFILE_REVISION_CONFLICT", "档案版本已更新", 409)
        if not c.data["profile"]: fail("PROFILE_INCOMPLETE", "请确认顾客条件")
        assets = db.scalars(select(Record).where(Record.kind == "asset", Record.parent_id == id)).all()
        views = {r.data["view"] for r in assets if r.data["kind"] == "original"}
        if "front" not in views or not views.intersection({"left", "right"}): fail("PHOTO_QUALITY_BLOCKED", "请提供正面及至少一张侧面照片")
        for j in db.scalars(select(Record).where(Record.kind == "job", Record.parent_id == id)):
            if j.data["status"] in ["queued", "running"]: fail("JOB_ACTIVE", "已有任务运行中", 409)
        modes = c.data["profile"]["modes"]
        if c.data["attempts_used"]+len(modes)*3 > 18: fail("BUDGET_EXCEEDED", "本次咨询的 18 次图像尝试额度不足")
        if c.data["mode"] == "real":
            if not configured(): fail("MODEL_NOT_CONFIGURED", "请配置两家模型 API 密钥", 503)
            if not c.data.get("analysis") or c.data["analysis"].get("blocking_issues"):
                fail("PHOTO_QUALITY_BLOCKED", "请先完成照片分析并解决严重质量问题")
        reservation = reserve_money(c, image_calls=len(modes)*3, vision_calls=len(modes)*4)
        change(c, status="generating")
        for old in db.scalars(select(Record).where(Record.kind == "candidate", Record.parent_id == id)):
            if old.data["profile_revision"] == c.revision: change(old, superseded=True)
        j = add(db, "job", c.salon_id, {"profile_revision": c.revision, "modes": modes, "status": "queued", "stage": "排队中", "completed": 0, "target": len(modes)*3, "reserved_cny": reservation, "heartbeat": time.time()}, id)
        change(record, result={"job_id": j.id, "status": "queued"})
        audit(db, user, "generation_started", id)
        return record.data["result"]

@app.get("/api/v1/jobs/{id}")
def job(id: str, user=Depends(auth)):
    with transaction() as db:
        r = get(db, id, user, "job")
        get(db, r.parent_id, user, "consultation")
        return public(r)

@app.post("/api/v1/jobs/{id}/cancel")
def cancel(id: str, user=Depends(auth)):
    with transaction() as db:
        r = get(db, id, user, "job")
        if r.data["status"] in ["queued", "running"]: change(r, cancel=True, status="cancelled" if r.data["status"] == "queued" else "running")
        return public(r)

class Review(BaseModel):
    candidate_revision: int
    profile_revision: int
    decision: Literal["approved", "rejected"]
    reason_codes: list[str] = Field(default_factory=list)
    viewed: bool

@app.post("/api/v1/candidates/{id}/reviews")
def review(id: str, body: Review, user=Depends(auth)):
    with transaction() as db:
        r = get(db, id, user, "candidate")
        c = get(db, r.parent_id, user, "consultation")
        if r.data.get("superseded") or body.profile_revision != c.revision or r.data["profile_revision"] != c.revision or body.candidate_revision != r.data["candidate_revision"]: fail("PROFILE_REVISION_CONFLICT", "方案版本已过期", 409)
        if body.decision == "approved" and (not body.viewed or r.data["gate"] != "pass" or r.data["issues"] or r.data["score"] is None or feasibility(c.data["profile"], r.data["plan"], r.data["mode"])): fail("REVIEW_REQUIRED", "请查看方案并解决限制条件后审核")
        if body.decision == "rejected" and not body.reason_codes: fail("REVIEW_REQUIRED", "请选择拒绝原因")
        change(r, review=body.decision, reviewed_by=user["id"])
        add(db, "review", c.salon_id, body.model_dump() | {"candidate_id": id, "reviewer": user["id"], "timestamp": now()}, c.id)
        return public(r)

class RevisionRequest(BaseModel):
    profile_revision: int
    candidate_revision: int
    adjustment: Literal["整体更自然", "刘海露额", "两侧更贴合", "顶部降低蓬松", "保留后区长度"]

@app.post("/api/v1/candidates/{id}/revision-jobs", status_code=202)
def revise(id: str, body: RevisionRequest, request: Request, user=Depends(auth)):
    with transaction() as db:
        r = get(db, id, user, "candidate")
        c = get(db, r.parent_id, user, "consultation")
        key, previous = idempotent(db, request, user, "revision", id, body.model_dump())
        if previous: return previous
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "照片授权已撤回")
        if r.data.get("superseded") or c.revision != body.profile_revision or r.data["candidate_revision"] != body.candidate_revision or r.data["profile_revision"] != c.revision: fail("PROFILE_REVISION_CONFLICT", "方案版本已更新", 409)
        if c.data["attempts_used"] >= 18: fail("BUDGET_EXCEEDED", "图像尝试次数不足")
        for job in db.scalars(select(Record).where(Record.kind == "job", Record.parent_id == c.id)):
            if job.data["status"] in ["queued", "running"]: fail("JOB_ACTIVE", "请等待当前任务完成", 409)
        plan = {**r.data["plan"], "description": r.data["plan"]["description"] + "；调整：" + body.adjustment}
        if body.adjustment == "刘海露额": plan["fringe"] = "露额"
        reservation = reserve_money(c, image_calls=1, vision_calls=1)
        change(c, status="generating")
        change(r, superseded=True)
        j = add(db, "job", c.salon_id, {"type": "revision", "previous_candidate_id": id, "candidate_revision": r.data["candidate_revision"]+1, "plan": plan, "profile_revision": c.revision, "modes": [r.data["mode"]], "status": "queued", "stage": "等待调整重做", "completed": 0, "target": 1, "reserved_cny": reservation, "heartbeat": time.time()}, c.id)
        change(key, result={"job_id": j.id, "status": "queued"})
        return key.data["result"]

class Delivery(BaseModel):
    candidate_ids: list[str] = Field(min_length=1)
    delivery_type: Literal["complete", "preview"] = "complete"
    demo: bool

@app.post("/api/v1/consultations/{id}/deliveries", status_code=201)
def delivery(id: str, body: Delivery, request: Request, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        key, previous = idempotent(db, request, user, "delivery", id, body.model_dump())
        if previous: return previous
        if not c.data["consent"]: fail("CONSENT_REQUIRED", "照片授权已撤回")
        if len(body.candidate_ids) != len(set(body.candidate_ids)): fail("DELIVERY_IMAGE_LIMIT", "请勿重复选择方案")
        if len(body.candidate_ids) > 9: fail("DELIVERY_IMAGE_LIMIT", "每个发布版本最多 9 张生成图")
        if body.demo != (c.data["mode"] == "demo"): fail("DEMO_DELIVERY_FORBIDDEN", "演示结果不能进入真实交付")
        candidates = []
        for cid in body.candidate_ids:
            r = get(db, cid, user, "candidate")
            if r.data.get("superseded") or r.parent_id != id or r.data["profile_revision"] != c.revision: fail("PROFILE_REVISION_CONFLICT", "方案与当前条件不一致", 409)
            if r.data["review"] != "approved" or r.data["gate"] != "pass" or r.data["score"] is None or r.data["issues"]: fail("REVIEW_REQUIRED", "只能展示已审核的合格方案")
            if r.data["demo"] != body.demo: fail("DEMO_DELIVERY_FORBIDDEN", "演示结果不能进入真实交付")
            if feasibility(c.data["profile"], r.data["plan"], r.data["mode"]): fail("REVIEW_REQUIRED", "方案存在未满足条件")
            candidates.append(r)
        if body.delivery_type == "complete":
            modes = c.data["profile"]["modes"]
            if any(sum(r.data["mode"] == m for r in candidates) < 3 for m in modes): fail("INSUFFICIENT_CANDIDATES", "完整展示需要每种已选模式至少 3 款；可改为阶段预览")
            if any(r.data["mode"] == "grow_out" and r.data["growth"]["month_min"] is None for r in candidates): fail("PROFILE_INCOMPLETE", "留发关键长度未知，只能发布条件性阶段预览")
        snapshot = [{k: r.data[k] for k in ["plan", "mode", "demo", "asset_id", "growth", "score"]} | {"candidate_id": r.id, "candidate_revision": r.data["candidate_revision"], "delivery_order": index+1} for index, r in enumerate(candidates)]
        d = add(db, "delivery", c.salon_id, {"snapshot": snapshot, "type": body.delivery_type, "demo": body.demo, "revoked": False, "profile_revision": c.revision, "published_by": user["id"]}, id)
        change(c, status="delivered")
        change(key, result={"delivery_id": d.id, "demo": body.demo})
        audit(db, user, "delivery_published", id)
        return key.data["result"]

@app.post("/api/v1/deliveries/{id}/presentation-session")
def presentation_session(id: str, response: Response, user=Depends(auth)):
    with transaction() as db:
        d = get(db, id, user, "delivery")
        c = get(db, d.parent_id, user, "consultation")
        if d.data["revoked"] or not c.data["consent"]: fail("NOT_FOUND", "展示已撤销", 404)
        token = secrets.token_urlsafe(32)
        add(db, "presentation", user["salon_id"], {"delivery_id": id, "expires": time.time()+1800}, c.id, token_hash(token))
        db.delete(db.get(Record, user["session_id"]))
        response.delete_cookie("salon_session")
        response.set_cookie("salon_presentation", token, httponly=True, secure=SECURE, samesite="strict", max_age=1800)
        return {"ok": True}

def presentation_data(db, request):
    raw = request.cookies.get("salon_presentation", "")
    s = db.get(Record, token_hash(raw)) if raw else None
    if not s or s.kind != "presentation" or s.data["expires"] < time.time(): fail("PRESENTATION_EXPIRED", "展示已结束，请交回发型师", 401)
    c = db.get(Record, s.parent_id)
    d = db.get(Record, s.data["delivery_id"])
    if not c or c.data.get("deleted") or not c.data["consent"] or not d or d.data["revoked"]: fail("NOT_FOUND", "展示已撤销", 404)
    return c, d

@app.get("/api/v1/presentation")
def presentation(request: Request):
    with transaction() as db:
        c, d = presentation_data(db, request)
        return {"customer_code": c.data["customer_code"], "delivery_id": d.id, "type": d.data["type"], "demo": d.data["demo"], "candidates": d.data["snapshot"]}

@app.get("/api/v1/presentation/assets/{id}")
def presentation_asset(id: str, request: Request):
    with transaction() as db:
        c, d = presentation_data(db, request)
        if id not in [r["asset_id"] for r in d.data["snapshot"]]: fail("NOT_FOUND", "资源不存在", 404)
        r = db.get(Record, id)
        if not r or r.parent_id != c.id: fail("NOT_FOUND", "资源不存在", 404)
        return FileResponse(r.data["path"], media_type="image/jpeg")

class Choice(BaseModel):
    candidate_id: str

@app.post("/api/v1/presentation/choice")
def presentation_choice(body: Choice, request: Request):
    if request.headers.get("X-Presentation-Action") != "choose": fail("CSRF_INVALID", "请求无效", 403)
    with transaction() as db:
        c, d = presentation_data(db, request)
        if body.candidate_id not in [r["candidate_id"] for r in d.data["snapshot"]]: fail("NOT_FOUND", "方案不存在", 404)
        add(db, "feedback", c.salon_id, {"type": "customer_selected", "candidate_id": body.candidate_id, "delivery_id": d.id}, c.id)
        return {"ok": True}

@app.post("/api/v1/presentation/exit")
def presentation_exit(request: Request, response: Response):
    if request.headers.get("X-Presentation-Action") != "exit": fail("CSRF_INVALID", "请求无效", 403)
    with transaction() as db:
        raw = request.cookies.get("salon_presentation", "")
        r = db.get(Record, token_hash(raw)) if raw else None
        if r and r.kind == "presentation": db.delete(r)
    response.delete_cookie("salon_presentation")
    return {"ok": True}

@app.delete("/api/v1/consultations/{id}")
def delete(id: str, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        for r in db.scalars(select(Record).where(Record.parent_id == id)):
            if r.kind == "asset": Path(r.data["path"]).unlink(missing_ok=True)
            if r.kind == "delivery": change(r, revoked=True)
            elif r.kind == "job": change(r, cancel=True)
            else: db.delete(r)
        change(c, deleted=True, consent=False, profile=None, customer_code="已删除", status="deleted")
        audit(db, user, "consultation_deleted", id)
        return {"ok": True}

class Feedback(BaseModel):
    candidate_id: str
    feasibility: Literal["可做", "需调整", "不可做"]
    executed: bool
    actual_deviation: Literal["未执行", "基本一致", "有偏差", "明显偏差"]

@app.post("/api/v1/consultations/{id}/feedback")
def feedback(id: str, body: Feedback, user=Depends(auth)):
    with transaction() as db:
        c = get(db, id, user, "consultation")
        r = get(db, body.candidate_id, user, "candidate")
        if r.parent_id != id: fail("NOT_FOUND", "方案不存在", 404)
        add(db, "feedback", c.salon_id, body.model_dump() | {"type": "stylist_actual_result", "operator": user["id"], "candidate_revision": r.data["candidate_revision"]}, id)
        audit(db, user, "actual_result_added", id)
        return {"ok": True}

class Account(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=12, max_length=200)
    role: Literal["admin", "stylist"] = "stylist"

@app.post("/api/v1/admin/users", status_code=201)
def account(body: Account, user=Depends(auth)):
    if user["role"] != "admin": fail("FORBIDDEN", "需要门店管理员权限", 403)
    with transaction() as db:
        if any(u.data["email"] == body.email for u in db.scalars(select(Record).where(Record.kind == "user"))): fail("ACCOUNT_EXISTS", "账号已存在", 409)
        r = add(db, "user", user["salon_id"], {**body.model_dump(exclude={"password"}), "password": password_hash(body.password)})
        audit(db, user, "account_created", r.id)
        return {"id": r.id, "name": body.name, "role": body.role}

@app.get("/api/v1/admin/metrics")
def metrics(user=Depends(auth)):
    if user["role"] != "admin": fail("FORBIDDEN", "需要门店管理员权限", 403)
    with transaction() as db:
        rows = list(db.scalars(select(Record).where(Record.salon_id == user["salon_id"])))
        counts = {kind: sum(r.kind == kind for r in rows) for kind in ["consultation", "candidate", "job", "delivery", "model_call", "feedback"]}
        return {"counts": counts, "job_failed": sum(r.kind == 'job' and r.data['status'] in ['failed', 'provider_result_unknown'] for r in rows), "candidate_rejected": sum(r.kind == 'candidate' and r.data['review'] == 'rejected' for r in rows), "reserved_cny": sum(r.data['reserved_cny'] for r in rows if r.kind == 'consultation'), "cost_status": "unreconciled", "actual_cost_cny": None, "note": "包含失败样本；演示与真实咨询需分开分析"}

@app.get("/api/v1/health")
def health(): return {"status": "ok", "mode": MODEL_MODE}

@app.get("/api/v1/client-config")
def client_config():
    return {"demo_login_allowed": os.getenv("PUBLIC_DEPLOYMENT") != "true" and MODEL_MODE == "demo"}

WEB_DIST = ROOT / "apps" / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="static")
    @app.get("/")
    def index(): return FileResponse(WEB_DIST / "index.html")
