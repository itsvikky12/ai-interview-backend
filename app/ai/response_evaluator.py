from __future__ import annotations
from app.ai import openai_client
from app.ai.prompt_templates import EVALUATE_RESPONSE, SKILL_GAP_ANALYSIS, INTERVIEW_SUMMARY
from app.utils.logger import get_logger

logger = get_logger(__name__)


def is_no_answer(answer: str | None) -> bool:
    if not answer:
        return True
    cleaned = answer.strip().lower()
    if not cleaned:
        return True
    
    exact_no_answers = {
        "",
        "(silence)",
        "(no answer provided)",
        "(candidate skipped this question)",
        "(failed to transcribe audio)",
        "pending evaluation...",
        "evaluating...",
        "skip",
        "pass",
        "next",
        "no answer",
        "no idea",
        "no clue",
        "don't know",
        "dont know",
        "i don't know",
        "i dont know",
        "i have no idea",
        "i don't know the answer",
        "i dont know the answer",
        "idk",
    }
    
    cleaned_no_punct = cleaned.strip(".,!?\"' ")
    if cleaned_no_punct in exact_no_answers or cleaned in exact_no_answers:
        return True
        
    words = [w.strip(".,!?\"'") for w in cleaned.split() if w.strip(".,!?\"'")]
    if not words:
        return True

    if len(words) <= 8:
        joined_clean = " ".join(words)
        refusal_phrases = ["don't know", "dont know", "no idea", "no clue", "skip", "pass", "not sure", "dont have any idea", "don't have any idea", "can't answer", "cant answer"]
        if any(phrase in joined_clean for phrase in refusal_phrases):
            return True
            
    return False


async def evaluate_response(
    question: str,
    question_type: str,
    expected_keywords: list[str],
    difficulty: float,
    answer: str,
) -> dict:
    if is_no_answer(answer):
        logger.info("response_evaluated_no_answer", question=question[:50])
        return {
            "score": 0.0,
            "technical_accuracy": 0.0,
            "depth": 0.0,
            "communication": 0.0,
            "relevance": 0.0,
            "feedback": "No answer was provided for this question.",
            "strengths": [],
            "weaknesses": ["candidate_response_incomplete_flag", "No answer provided"],
            "should_follow_up": False,
            "difficulty_adjustment": -1,
        }

    prompt = EVALUATE_RESPONSE.format(
        question=question,
        question_type=question_type,
        expected_keywords=", ".join(expected_keywords) if expected_keywords else "None specified",
        difficulty=difficulty,
        answer=answer[:2000],
    )

    messages = [
        {"role": "system", "content": "You are a fair, rigorous technical interviewer. Always respond with valid JSON."},
        {"role": "user", "content": prompt},
    ]

    result = await openai_client.chat_completion_json(messages, temperature=0.3)

    evaluation = {
        "score": min(10.0, max(0.0, float(result.get("score", 5.0)))),
        "technical_accuracy": float(result.get("technical_accuracy", 5.0)),
        "depth": float(result.get("depth", 5.0)),
        "communication": float(result.get("communication", 5.0)),
        "relevance": float(result.get("relevance", 5.0)),
        "feedback": result.get("feedback", ""),
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "should_follow_up": result.get("should_follow_up", False),
        "difficulty_adjustment": int(result.get("difficulty_adjustment", 0)),
    }

    logger.info("response_evaluated", score=evaluation["score"], follow_up=evaluation["should_follow_up"])
    return evaluation


async def analyze_skill_gaps(target_role: str, skills: list[dict], performance: dict) -> dict:
    skills_text = "\n".join(
        f"- {s.get('name', '')}: {s.get('proficiency', 'unknown')}" for s in skills[:20]
    )

    prompt = SKILL_GAP_ANALYSIS.format(
        target_role=target_role,
        skills=skills_text,
        performance=str(performance)[:2000],
    )

    messages = [
        {"role": "system", "content": "You are a career coach and technical assessor. Always respond with valid JSON."},
        {"role": "user", "content": prompt},
    ]

    return await openai_client.chat_completion_json(messages, temperature=0.4)


async def generate_interview_summary(
    candidate_name: str,
    target_role: str,
    question_scores: list[dict],
    avg_technical: float,
    avg_communication: float,
    speech_metrics: dict | None,
    anti_cheat_flags: dict | None,
) -> dict:
    non_zero_scores = [qs.get("score", 0.0) for qs in question_scores if qs.get("score", 0.0) > 0]
    if not non_zero_scores or (avg_technical == 0.0 and avg_communication == 0.0):
        return {
            "executive_summary": f"The candidate {candidate_name} did not provide answers to the interview questions. As a result, technical and communication competencies could not be evaluated.",
            "technical_analysis": "No technical answers were submitted during the assessment.",
            "communication_analysis": "No responses were spoken or provided to evaluate communication ability.",
            "top_strengths": [],
            "critical_improvements": ["Ensure to answer interview questions actively with detailed explanations."],
            "hire_recommendation": "Do Not Hire",
            "confidence_in_assessment": 100,
        }

    scores_text = "\n".join(
        f"Q: {qs.get('question', '')[:100]} → Score: {qs.get('score', 0)}/10, Feedback: {qs.get('feedback', '')[:100]}"
        for qs in question_scores
    )

    prompt = INTERVIEW_SUMMARY.format(
        candidate_name=candidate_name,
        target_role=target_role,
        question_scores=scores_text,
        avg_technical=f"{avg_technical:.1f}",
        avg_communication=f"{avg_communication:.1f}",
        speech_metrics=str(speech_metrics or {}),
        anti_cheat_flags=str(anti_cheat_flags or {}),
    )

    messages = [
        {"role": "system", "content": "You are a senior hiring manager writing interview assessments. Always respond with valid JSON."},
        {"role": "user", "content": prompt},
    ]

    return await openai_client.chat_completion_json(messages, temperature=0.4)

