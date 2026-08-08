from __future__ import annotations

from app.ai import openai_client
from app.ai import prompt_templates as prompts
from app.models.interview import InterviewPhase
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _build_resume_summary(resume_data: dict | None) -> str:
    if not resume_data:
        return "No resume provided."

    parts = []

    # 1. Summary
    summary = resume_data.get("summary", "")
    if summary:
        parts.append(f"Summary: {summary}")

    # 2. Skills (Categorized for clarity)
    skills = resume_data.get("skills") or []
    if skills:
        categorized_skills = {}
        for s in skills:
            if isinstance(s, dict):
                name = s.get("name", "")
                cat = s.get("category", "other").replace("_", " ").title()
                if cat not in categorized_skills:
                    categorized_skills[cat] = []
                categorized_skills[cat].append(name)
            else:
                if "General" not in categorized_skills:
                    categorized_skills["General"] = []
                categorized_skills["General"].append(str(s))
        
        skills_str = "Skills by Category:\n"
        for cat, names in categorized_skills.items():
            skills_str += f"- {cat}: {', '.join(names)}\n"
        parts.append(skills_str.strip())

    # 3. Work Experience & Internship Experience
    experience = resume_data.get("experience") or []
    if experience:
        work_exp = []
        intern_exp = []
        for exp in experience:
            if isinstance(exp, dict):
                exp_type = exp.get("type", "job")
                desc = exp.get("description", "")
                highlights = exp.get("highlights", [])
                techs = exp.get("technologies", [])
                
                exp_str = f"- {exp.get('title', '')} at {exp.get('company', '')}"
                if exp.get('start_date') or exp.get('end_date'):
                    exp_str += f" ({exp.get('start_date', '')} - {exp.get('end_date', '')})"
                if desc:
                    exp_str += f"\n  Description: {desc}"
                if highlights:
                    exp_str += f"\n  Highlights: {'; '.join(highlights)}"
                if techs:
                    exp_str += f"\n  Technologies: {', '.join(techs)}"
                
                if exp_type == "internship":
                    intern_exp.append(exp_str)
                else:
                    work_exp.append(exp_str)
                    
        if work_exp:
            parts.append("Work Experience:\n" + "\n".join(work_exp))
        if intern_exp:
            parts.append("Internship Experience:\n" + "\n".join(intern_exp))

    # 4. Projects
    projects = resume_data.get("projects") or []
    if projects:
        proj_parts = []
        for proj in projects:
            if isinstance(proj, dict):
                proj_str = f"- Project: {proj.get('name', '')}"
                desc = proj.get('description', '')
                techs = proj.get('technologies', [])
                highlights = proj.get('highlights', [])
                if desc:
                    proj_str += f"\n  Description: {desc}"
                if techs:
                    proj_str += f"\n  Technologies: {', '.join(techs)}"
                if highlights:
                    proj_str += f"\n  Highlights: {'; '.join(highlights)}"
                proj_parts.append(proj_str)
        parts.append("Projects:\n" + "\n".join(proj_parts))

    # 5. Certifications
    certs = resume_data.get("certifications") or []
    if certs:
        cert_names = [c.get("name") if isinstance(c, dict) else str(c) for c in certs]
        parts.append(f"Certifications: {', '.join(cert_names)}")

    # 6. Research Papers
    papers = resume_data.get("research_papers") or []
    if papers:
        paper_parts = []
        for p in papers:
            if isinstance(p, dict):
                title = p.get("title", "")
                desc = p.get("description", "")
                p_str = f"- {title}"
                if desc:
                    p_str += f": {desc}"
                paper_parts.append(p_str)
            else:
                paper_parts.append(f"- {str(p)}")
        parts.append("Research Papers:\n" + "\n".join(paper_parts))

    # 7. Education
    edu = resume_data.get("education") or []
    if edu:
        edu_parts = []
        for e in edu:
            if isinstance(e, dict):
                e_str = f"- {e.get('degree', '')} in {e.get('field', '')} from {e.get('institution', '')}"
                if e.get("gpa"):
                    e_str += f" (GPA: {e.get('gpa')})"
                edu_parts.append(e_str)
        parts.append("Education:\n" + "\n".join(edu_parts))

    # 8. Achievements
    achievements = resume_data.get("achievements") or []
    if achievements:
        ach_parts = [f"- {str(a)}" for a in achievements]
        parts.append("Achievements:\n" + "\n".join(ach_parts))

    return "\n\n".join(parts) if parts else "Minimal resume data available."


def _build_conversation_history(messages: list[dict]) -> str:
    if not messages:
        return "This is the first question."

    history_parts = []
    for msg in messages[-6:]:
        role = msg.get("role", "")
        content = msg.get("content", "")[:300]
        if role == "interviewer":
            history_parts.append(f"Q: {content}")
        elif role == "candidate":
            history_parts.append(f"A: {content}")
    return "\n".join(history_parts)


async def generate_question(
    phase: InterviewPhase,
    target_role: str,
    difficulty: float,
    language: str,
    resume_data: dict | None,
    conversation_history: list[dict],
    existing_questions: list[str] | None = None,
    last_answer: str | None = None,
    last_question: str | None = None,
    needs_follow_up: bool = False,
) -> dict:
    resume_summary = _build_resume_summary(resume_data)
    history_text = _build_conversation_history(conversation_history)

    existing_questions_str = "None."
    if existing_questions:
        unique_qs = []
        for q in existing_questions:
            q_stripped = q.strip()
            if q_stripped and q_stripped not in unique_qs:
                unique_qs.append(q_stripped)
        if unique_qs:
            existing_questions_str = "\n".join([f"- {q}" for q in unique_qs])

    system_prompt = prompts.QUESTION_GENERATION_SYSTEM.format(
        target_role=target_role,
        phase=phase.value,
        difficulty=difficulty,
        language=language,
        resume_summary=resume_summary,
        conversation_history=history_text,
        existing_questions=existing_questions_str,
    )

    if needs_follow_up and last_answer and last_question:
        topic = "technical" if phase == InterviewPhase.TECHNICAL else phase.value
        user_prompt = prompts.QUESTION_FOLLOW_UP.format(
            last_answer=last_answer[:500],
            last_question=last_question[:500],
            topic=topic,
        )
    elif phase == InterviewPhase.INTRODUCTION:
        user_prompt = prompts.QUESTION_INTRO
    elif phase == InterviewPhase.TECHNICAL:
        user_prompt = prompts.QUESTION_TECHNICAL.format(difficulty=difficulty)
    elif phase == InterviewPhase.SYSTEM_DESIGN:
        user_prompt = prompts.QUESTION_SYSTEM_DESIGN.format(difficulty=difficulty)
    elif phase == InterviewPhase.HR:
        user_prompt = prompts.QUESTION_HR
    else:
        user_prompt = prompts.QUESTION_TECHNICAL.format(difficulty=difficulty)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = await openai_client.chat_completion_json(messages, temperature=0.7)

    question_data = {
        "question": result.get("question", "Could you tell me more about your experience?"),
        "topic": result.get("topic", phase.value),
        "expected_keywords": result.get("expected_keywords", []),
    }

    logger.info("question_generated", phase=phase.value, difficulty=difficulty, topic=question_data["topic"])
    return question_data


async def generate_interview_path(
    target_role: str,
    language: str,
    resume_data: dict | None,
) -> list[dict]:
    resume_summary = _build_resume_summary(resume_data)

    system_prompt = prompts.PATH_GENERATION_SYSTEM.format(
        target_role=target_role,
        language=language,
        resume_summary=resume_summary,
    )
    user_prompt = prompts.PATH_GENERATION_USER

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = await openai_client.chat_completion_json(messages, temperature=0.7)
        questions = result.get("questions", [])
        if len(questions) == 5:
            # Validate each question item contains keys
            validated = []
            for idx, q in enumerate(questions):
                validated.append({
                    "order_index": idx + 1,
                    "question_text": q.get("question_text", "Tell me more."),
                    "question_type": q.get("question_type", "technical"),
                    "topic": q.get("topic", "Technical"),
                    "difficulty": float(q.get("difficulty", 6.0)),
                    "expected_keywords": q.get("expected_keywords", [])
                })
            return validated
    except Exception as e:
        logger.error("path_generation_failed", error=str(e))
    return []

