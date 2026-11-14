import os
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from PIL import Image
import io
from .db import transaction, Record, add, change, DATA, now
from .providers import VisionProvider, ImageProvider, ProviderFailure, configured_price
from .rules import score, growth, feasibility, deduplicate

DEMO_STYLES = [
    ("轻盈短碎", "short_crop", "轻薄刘海", "自然分缝", "碎发纹理", [1, 3, 1, 1], False),
    ("利落侧分", "side_part", "侧扫刘海", "侧分", "顺直线条", [3, 3, 1, 1], False),
    ("自然层次", "layered", "空气刘海", "中分", "柔和层次", [3, 3, 3, 3], False),
    ("耳际短鲍勃", "bob", "无刘海", "偏分", "整齐轮廓", [5, 8, 5, 5], False),
    ("锁骨层次", "lob", "八字刘海", "中分", "轻盈层次", [8, 12, 12, 12], True),
    ("长发柔线", "long_layered", "长刘海", "侧分", "自然直发", [8, 12, 12, 12], True),
    ("露额短发", "crop_open", "露额", "自然分缝", "贴合纹理", [1, 1, 1, 1], False),
    ("长层次中分", "long_center", "长刘海", "中分", "纵向层次", [8, 12, 12, 12], True),
]

def demo_plans():
    return [{"name": n, "family": f, "fringe": fr, "parting": p, "texture": t, "minimum_lengths": dict(zip(["fringe", "top", "sides", "back"], lengths)), "description": f"{fr} · {p} · {t}", "reason": "演示用结构示例，未经过专业验证，不代表适合当前顾客。", "maintenance": "维护要求需发型师确认", "required_services": [], "minimum_density": "不限制", "tie_back_supported": tie} for n, f, fr, p, t, lengths, tie in DEMO_STYLES]

def active(db, job_id):
    j = db.get(Record, job_id, with_for_update=True)
    c = db.get(Record, j.parent_id, with_for_update=True)
    if c.data.get("deleted") or c.revision != j.data["profile_revision"] or j.data.get("cancel"):
        change(j, status="cancelled", stage="条件更新或任务取消", updated_at=now())
        if not c.data.get("deleted") and c.revision == j.data["profile_revision"]: change(c, status="partial")
        return None, None
    change(j, heartbeat=time.time())
    return j, c

def log_call(db, j, meta, reservation):
    add(db, "model_call", j.salon_id, {**meta, "reserved_cny": reservation, "prompt_version": "v0.1", "actual_cost_cny": None}, j.id)

def run_job(job_id):
    with transaction() as db:
        j, c = active(db, job_id)
        if j is None: return
        salon, profile, mode_real = c.salon_id, c.data["profile"], c.data["mode"] == "real"
        modes, rev = j.data["modes"], c.revision
        assets = [a for a in db.scalars(select(Record).where(Record.kind == "asset", Record.parent_id == c.id)) if a.data.get("kind") == "original"]
        assets.sort(key=lambda a: 0 if a.data["view"] == "front" else 1)
        originals = [Path(a.data["path"]).read_bytes() for a in assets] if mode_real else []
        job_type = j.data.get("type", "generate")
        if job_type != "analysis": profile = c.data["profile"]
    try:
        if job_type == "analysis":
            result, meta = VisionProvider().analyze(originals) if mode_real else ({"observations": ["演示模式不分析照片内容，请发型师检查模糊、曝光、人数、裁切和角度。"], "unknown_fields": ["发长", "密度", "发质"], "photo_issues": [], "blocking_issues": [], "demo": True}, None)
            if not all(isinstance(result.get(k), list) for k in ["observations", "unknown_fields", "photo_issues", "blocking_issues"]): raise ProviderFailure("SCHEMA_INVALID")
            with transaction() as db:
                j, c = active(db, job_id)
                if j is None: return
                change(c, analysis=result)
                change(j, status="succeeded", stage="分析完成，待人工确认", completed=1)
                if meta: log_call(db, j, meta, j.data["reserved_cny"])
            return
        for mode in modes:
            with transaction() as db:
                j, c = active(db, job_id)
                if j is None: return
                change(j, stage="规划方案", heartbeat=time.time())
            if job_type == "revision":
                plans, meta = [j.data["plan"]], None
            else:
                plans, meta = VisionProvider().plan(profile, mode) if mode_real else (demo_plans(), None)
            if meta:
                with transaction() as db:
                    log_call(db, db.get(Record, job_id), meta, configured_price("VISION_CALL_RESERVE_CNY"))
            plans = [p for p in deduplicate(plans) if not feasibility(profile, p, mode)]
            if mode == "grow_out": plans = list(reversed(plans))
            for i, plan in enumerate(plans[:3]):
                with transaction() as db:
                    j, c = active(db, job_id)
                    if j is None: return
                    if c.data["attempts_used"] >= 18: break
                    change(c, attempts_used=c.data["attempts_used"]+1)
                    change(j, stage="生成与质检", heartbeat=time.time())
                image_path, evaluation = None, None
                if mode_real:
                    image, image_meta = ImageProvider().generate(originals, profile, plan)
                    # Decoding checks occur before retaining generated images.
                    with Image.open(io.BytesIO(image)) as decoded:
                        if decoded.width * decoded.height > 40_000_000: raise ProviderFailure("SCHEMA_INVALID")
                        decoded.load()
                        path = DATA / "assets" / f"{job_id}-{mode}-{i}.jpg"
                        path.parent.mkdir(exist_ok=True)
                        decoded.convert("RGB").save(path, "JPEG", quality=92)
                        image_path = str(path)
                    evaluation, eval_meta = VisionProvider().evaluate(originals, path.read_bytes(), profile, plan)
                    with transaction() as db:
                        j = db.get(Record, job_id)
                        log_call(db, j, image_meta, configured_price("IMAGE_ATTEMPT_PRICE_CNY"))
                        log_call(db, j, eval_meta, configured_price("VISION_CALL_RESERVE_CNY"))
                with transaction() as db:
                    j, c = active(db, job_id)
                    if j is None:
                        if image_path: Path(image_path).unlink(missing_ok=True)
                        return
                    asset_id = None
                    if image_path: asset_id = add(db, "asset", salon, {"path": image_path, "kind": "generated", "view": "front"}, c.id).id
                    dimensions = evaluation["dimensions"] if evaluation else {"visual_balance": 4, "feasibility": 4, "preference_match": 4, "maintenance_match": 3, "transition_ease": 3}
                    total = score(dimensions, mode)
                    add(db, "candidate", salon, {"plan": plan, "mode": mode, "demo": not mode_real, "profile_revision": rev, "candidate_revision": j.data.get("candidate_revision", 1), "previous_candidate_id": j.data.get("previous_candidate_id"), "asset_id": asset_id, "dimensions": dimensions, "score": total, "issues": evaluation["issues"] if evaluation else [], "gate": evaluation["gate_status"] if evaluation else "pass", "review": "pending", "growth": growth(profile["lengths"], plan["minimum_lengths"]) if mode == "grow_out" else None}, c.id)
                    change(j, completed=j.data["completed"]+1)
        with transaction() as db:
            j, c = active(db, job_id)
            if j is None: return
            counts = {m: db.scalars(select(Record).where(Record.kind == "candidate", Record.parent_id == c.id)).all() for m in modes}
            sufficient = all(len([r for r in records if not r.data.get("superseded") and r.data["mode"] == m and r.data["profile_revision"] == rev and r.data["gate"] == "pass" and r.data["score"] is not None]) >= 3 for m, records in counts.items())
            change(j, status="succeeded" if sufficient else "partial", stage="等待审核" if sufficient else "结果不足", updated_at=now())
            change(c, status="review_ready" if sufficient else "partial")
    except Exception as exc:
        code = exc.code if isinstance(exc, ProviderFailure) else "SCHEMA_INVALID" if isinstance(exc, ValueError) else "WORKER_ERROR"
        with transaction() as db:
            j = db.get(Record, job_id, with_for_update=True)
            c = db.get(Record, j.parent_id, with_for_update=True)
            change(j, status="provider_result_unknown" if code == "PROVIDER_RESULT_UNKNOWN" else "failed", stage="调用未完成", error=code, updated_at=now())
            if not c.data.get("deleted") and c.revision == j.data["profile_revision"]: change(c, status="failed")

def tick():
    with transaction() as db:
        jobs = db.scalars(select(Record).where(Record.kind == "job").with_for_update(skip_locked=True)).all()
        for j in jobs:
            if j.data["status"] == "running" and time.time()-j.data.get("heartbeat", 0) > 600:
                # External effects may already exist. Never blindly replay paid calls.
                change(j, status="provider_result_unknown", error="PROVIDER_RESULT_UNKNOWN", stage="任务中断，需核对")
                c = db.get(Record, j.parent_id, with_for_update=True)
                if c and not c.data.get("deleted") and c.revision == j.data["profile_revision"]: change(c, status="failed")
            if j.data["status"] == "queued":
                change(j, status="running", heartbeat=time.time())
                job_id = j.id
                break
        else: return False
    run_job(job_id)
    return True

def loop(stop=None):
    while stop is None or not stop.is_set():
        if not tick():
            if stop: stop.wait(.5)
            else: time.sleep(.5)

if __name__ == "__main__": loop()
