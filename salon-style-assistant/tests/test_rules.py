import pytest
from app.rules import score, growth, feasibility, LENGTHS, WEIGHTS, deduplicate
from app.worker import demo_plans

@pytest.mark.parametrize('mode', ['current', 'grow_out'])
def test_scores(mode):
    assert sum(WEIGHTS[mode]) == 100
    assert score(dict.fromkeys(['visual_balance','feasibility','preference_match','maintenance_match','transition_ease'], 5), mode) == 100
    assert score({'visual_balance': 5}, mode) is None

@pytest.mark.parametrize('invalid', [-1, 6, True])
def test_score_range(invalid):
    values = dict.fromkeys(['visual_balance','feasibility','preference_match','maintenance_match','transition_ease'], invalid)
    with pytest.raises(ValueError): score(values, 'current')

def test_growth_range_outward_rounding():
    g = growth({'top': '3-5'}, {'top': 11})
    assert (g['month_min'], g['month_max']) == (5, 10)
    assert growth({'top': 'unknown'}, {'top': 11})['month_min'] is None
    assert growth({'top': '20+'}, {'top': 25})['month_max'] is None
    assert growth({'top': '3-5'}, {'top': 11}, False)['month_max'] is None
    assert growth({'top': '12-20'}, {'top': 8})['month_max'] == 0

def test_constraints_unknown_not_accepted():
    plan = {'minimum_lengths': {'top': 3}, 'required_services': ['perm'], 'tie_back_supported': False}
    issues = feasibility({'perm_acceptance': '可讨论', 'tie_back_need': '必须', 'lengths': {'top': 'unknown'}}, plan, 'current')
    assert '烫发依赖尚未得到明确接受' in issues
    assert '化学处理条件需要发型师进一步判断' in issues
    assert '必须满足扎发要求' in issues
    assert 'top 最低长度未确认满足' in issues

def test_length_boundaries_and_dedup():
    assert LENGTHS['3-5'][1] == LENGTHS['5-8'][0]
    plans = demo_plans()
    assert len(deduplicate(plans + plans)) == len(plans)
