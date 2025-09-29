from apps.api.services.planner import QueryPlanner


def test_query_planner_intent_detection():
    planner = QueryPlanner()
    plan = planner.plan("When was Project Alpha kickoff?")
    assert plan.intent == "temporal"
    assert "Project Alpha" in plan.entities
    assert "time_range" in plan.filters


def test_query_planner_entity_focus():
    planner = QueryPlanner()
    plan = planner.plan("Who emailed Alice about onboarding?")
    assert plan.intent == "entity"
    assert "Alice" in plan.entities
