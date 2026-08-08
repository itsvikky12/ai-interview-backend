import pytest
from app.services.interview_flow_service import InterviewFlowService

@pytest.mark.asyncio
async def test_easy_round_flow_config(db_session):
    service = InterviewFlowService(db_session)
    config = await service.get_round_configuration("easy")

    assert config["selected_difficulty"] == "Easy"
    assert config["total_questions"] == 2
    assert config["total_time_minutes"] == 30

    questions = config["questions"]
    assert len(questions) == 2

    # Question 1: Easy SQL/MySQL Question (10 min)
    q1 = questions[0]
    assert q1["type"] == "SQL"
    assert q1["topic"] == "SQL/MySQL"
    assert q1["difficulty"] == "Easy"
    assert q1["time_limit_minutes"] == 10
    assert q1["time_limit_seconds"] == 600

    # Question 2: Medium DSA Coding Question (20 min)
    q2 = questions[1]
    assert q2["type"] == "DSA Coding"
    assert q2["topic"] == "DSA"
    assert q2["difficulty"] == "Medium"
    assert q2["time_limit_minutes"] == 20
    assert q2["time_limit_seconds"] == 1200


@pytest.mark.asyncio
async def test_medium_round_flow_config(db_session):
    service = InterviewFlowService(db_session)
    config = await service.get_round_configuration("medium")

    assert config["selected_difficulty"] == "Medium"
    assert config["total_questions"] == 2
    assert config["total_time_minutes"] == 30

    questions = config["questions"]
    assert len(questions) == 2

    # Question 1: Easy SQL/MySQL Question (10 min)
    q1 = questions[0]
    assert q1["type"] == "SQL"
    assert q1["topic"] == "SQL/MySQL"
    assert q1["difficulty"] == "Easy"
    assert q1["time_limit_minutes"] == 10

    # Question 2: Medium DSA Coding Question (20 min)
    q2 = questions[1]
    assert q2["type"] == "DSA Coding"
    assert q2["topic"] == "DSA"
    assert q2["difficulty"] == "Medium"
    assert q2["time_limit_minutes"] == 20


@pytest.mark.asyncio
async def test_hard_round_flow_config(db_session):
    service = InterviewFlowService(db_session)
    config = await service.get_round_configuration("hard")

    assert config["selected_difficulty"] == "Hard"
    assert config["total_questions"] == 1
    assert config["total_time_minutes"] == 30

    questions = config["questions"]
    assert len(questions) == 1

    # Question 1: Hard DSA Coding Question ONLY (30 min)
    q1 = questions[0]
    assert q1["type"] == "DSA Coding"
    assert q1["topic"] == "DSA"
    assert q1["difficulty"] == "Hard"
    assert q1["time_limit_minutes"] == 30
    assert q1["time_limit_seconds"] == 1800
