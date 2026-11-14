"""Deterministic rules; neither a beauty score nor professional measurement."""
import math

WEIGHTS = {"current": [30, 30, 20, 15, 5], "grow_out": [35, 20, 20, 15, 10]}
DIMENSIONS = ["visual_balance", "feasibility", "preference_match", "maintenance_match", "transition_ease"]
ZONES = ["fringe", "top", "sides", "back"]
# Lower-inclusive, upper-exclusive; measured lengths use equal endpoints.
LENGTHS = {"unknown": None, "0-1": [0, 1], "1-3": [1, 3], "3-5": [3, 5], "5-8": [5, 8], "8-12": [8, 12], "12-20": [12, 20], "20+": [20, None]}

def score(dimensions, mode):
    values = [dimensions.get(k) for k in DIMENSIONS]
    if any(v is None for v in values):
        return None
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 5 for v in values):
        raise ValueError("分项分数必须介于 0～5")
    return math.floor(sum(v / 5 * w for v, w in zip(values, WEIGHTS[mode])) + .5)

def growth(lengths, targets, density_ok=True):
    if not density_ok:
        return {"month_min": None, "month_max": None, "reason": "密度条件不能通过等待满足"}
    bounds = []
    for zone, target in targets.items():
        current = LENGTHS.get(lengths.get(zone, "unknown"))
        if current is None or current[1] is None:
            return {"month_min": None, "month_max": None, "reason": "请补充关键区域的长度测量"}
        bounds.append((max(0, target-current[1])/1.2, max(0, target-current[0])/.8))
    return {"month_min": math.floor(max((b[0] for b in bounds), default=0)), "month_max": math.ceil(max((b[1] for b in bounds), default=0)), "reason": "按每月 0.8～1.2 cm 情景估算，未计修剪和断发；不是个人生长承诺"}

def feasibility(profile, plan, mode):
    issues = []
    if "perm" in plan.get("required_services", []) and profile.get("perm_acceptance") != "接受":
        issues.append("烫发依赖尚未得到明确接受")
    if "perm" in plan.get("required_services", []) and (profile.get("damage_observation") != "无明显问题" or "不确定" in profile.get("treatment_history", ["不确定"])):
        issues.append("化学处理条件需要发型师进一步判断")
    if profile.get("fringe_preference") == "不要刘海" and plan.get("fringe") not in ["露额", "无刘海"]:
        issues.append("顾客明确不要刘海")
    if profile.get("tie_back_need") == "必须" and not plan.get("tie_back_supported"):
        issues.append("必须满足扎发要求")
    if plan.get("minimum_density") == "中等" and profile.get("density") in ["偏少", "不确定"]:
        issues.append("密度条件不满足或待确认")
    if mode == "current":
        for zone, target in plan.get("minimum_lengths", {}).items():
            length = LENGTHS.get(profile.get("lengths", {}).get(zone, "unknown"))
            if length is None or length[0] < target:
                issues.append(f"{zone} 最低长度未确认满足")
    if mode == "grow_out":
        horizon = {"3 个月内": 3, "半年内": 6, "一年内": 12}.get(profile.get("waiting_horizon"))
        estimate = growth(profile.get("lengths", {}), plan.get("minimum_lengths", {}))
        if horizon is not None and estimate["month_max"] is not None and estimate["month_max"] > horizon:
            issues.append("超出顾客接受的留发时间")
    return issues

def deduplicate(plans):
    seen, result = set(), []
    for plan in plans:
        key = tuple(plan[k] for k in ("family", "fringe", "parting", "texture"))
        if key not in seen:
            seen.add(key)
            result.append(plan)
    return result
