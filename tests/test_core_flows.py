"""
==========================================================================
  DIRECT SERVICE-LAYER VERIFICATION
  
  Tests the 3 core AI flows at the service/module level:
    1. Resume Upload → AI Parsing → Structured Data
    2. AI Question Generation (all 5 phases)  
    3. AI Answer Evaluation → Scoring → Adaptive Difficulty
    
  No HTTP, no SQLite, no database — pure logic verification.
==========================================================================
"""
import asyncio
import os
import sys
import json

os.environ["DEBUG"] = "true"
os.environ["JWT_SECRET_KEY"] = "k" * 40
os.environ["OPENAI_API_KEY"] = "x"

# ── Mock OpenAI BEFORE any imports ──
import app.ai.openai_client as oai

CALL_LOG = []

async def mock_completion_json(messages, **kwargs):
    # Find system prompt and user prompt
    system_content = ""
    user_content = ""
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            system_content = content
        elif role == "user":
            user_content = content
            
    sys_lower = system_content.lower()
    user_lower = user_content.lower()
    
    call_info = {
        "content_preview": (sys_lower + " | " + user_lower)[:80],
        "messages": messages
    }
    
    if "expert resume parser" in sys_lower:
        call_info["matched"] = "RESUME_PARSE"
        CALL_LOG.append(call_info)
        return {
            "skills": [
                {"name": "Python", "category": "programming_language", "proficiency": "advanced"},
                {"name": "FastAPI", "category": "framework", "proficiency": "advanced"},
                {"name": "React", "category": "framework", "proficiency": "intermediate"},
                {"name": "PostgreSQL", "category": "database", "proficiency": "advanced"},
                {"name": "Docker", "category": "tool", "proficiency": "intermediate"},
            ],
            "projects": [{"name": "E-Commerce Platform", "description": "Full-stack marketplace", "technologies": ["Python", "FastAPI", "React"], "highlights": ["10K users"]}],
            "experience": [{"company": "TechCorp", "title": "Senior SWE", "type": "job", "start_date": "2021", "end_date": "2024", "description": "Led backend team", "highlights": ["40% latency reduction"], "technologies": ["Python", "FastAPI"]}],
            "education": [{"institution": "IIT", "degree": "B.Tech", "field": "CS", "gpa": "8.5"}],
            "certifications": ["AWS SA Associate"],
            "research_papers": [{"title": "AWS and Cloud Systems", "description": "A paper on cloud scalability"}],
            "achievements": ["Dean's List 2023"],
            "summary": "Senior backend engineer with 3+ years in Python microservices."
        }
    elif "career coach and technical assessor" in sys_lower:
        call_info["matched"] = "SKILL_GAP"
        CALL_LOG.append(call_info)
        return {"matching_skills": [{"skill": "Python", "assessment": "Strong"}], "missing_skills": [{"skill": "K8s", "importance": "critical", "learning_resource": "k8s.io"}], "improvement_roadmap": [{"week": "1-2", "focus": "Containers", "actions": ["Docker", "K8s"]}], "overall_readiness": 68, "summary": "Strong backend, needs cloud-native."}
    elif "senior hiring manager" in sys_lower:
        call_info["matched"] = "INTERVIEW_SUMMARY"
        CALL_LOG.append(call_info)
        return {
            "summary": "Solid candidate.",
            "executive_summary": "Solid candidate.",
            "technical_analysis": "Demonstrated solid technical foundation.",
            "communication_analysis": "Clear communication.",
            "top_strengths": ["Python"],
            "critical_improvements": ["System design"],
            "hire_recommendation": "yes",
            "confidence_in_assessment": 82
        }
    elif "fair, rigorous technical interviewer" in sys_lower:
        call_info["matched"] = "EVALUATE_RESPONSE"
        CALL_LOG.append(call_info)
        return {
            "score": 7.8, "technical_accuracy": 8.5, "depth": 7.0,
            "communication": 7.5, "relevance": 8.0,
            "feedback": "Strong understanding of connection pooling. Good use of pgbouncer. Consider discussing monitoring strategies.",
            "strengths": ["Clear architecture explanation", "Practical real-world experience", "Good trade-off analysis"],
            "weaknesses": ["Could discuss monitoring metrics", "Missing connection timeout strategies"],
            "should_follow_up": True, "difficulty_adjustment": 1,
        }
    elif "senior technical interviewer at a top tech company" in sys_lower:
        if "follow-up" in user_lower or "follow_up" in user_lower or "follow up" in user_lower:
            call_info["matched"] = "QUESTION_FOLLOWUP"
            CALL_LOG.append(call_info)
            return {"question": "What monitoring did you use for pool exhaustion?", "topic": "database_optimization", "expected_keywords": ["prometheus", "grafana"]}
        elif "current phase: introduction" in sys_lower:
            call_info["matched"] = "QUESTION_INTRODUCTION"
            CALL_LOG.append(call_info)
            return {"question": "Tell me about your most impactful project at TechCorp.", "topic": "introduction", "expected_keywords": []}
        elif "current phase: technical" in sys_lower:
            call_info["matched"] = "QUESTION_TECHNICAL"
            CALL_LOG.append(call_info)
            return {"question": "How would you design connection pooling for 10K concurrent requests?", "topic": "database_optimization", "expected_keywords": ["pool", "pgbouncer", "async"]}
        elif "current phase: system_design" in sys_lower:
            call_info["matched"] = "QUESTION_SYSTEM_DESIGN"
            CALL_LOG.append(call_info)
            return {"question": "Design a real-time notification system for 50M users.", "topic": "system_design", "expected_keywords": ["kafka", "queue"]}
        elif "current phase: hr" in sys_lower:
            call_info["matched"] = "QUESTION_HR"
            CALL_LOG.append(call_info)
            return {"question": "Tell me about a technical disagreement you resolved.", "topic": "behavioral", "expected_keywords": []}
            
    call_info["matched"] = "FALLBACK"
    CALL_LOG.append(call_info)
    return {"question": "Can you elaborate?", "topic": "general", "expected_keywords": []}

oai.chat_completion_json = mock_completion_json

# ── Now import the modules under test ──
from app.ai.resume_parser import parse_resume
from app.ai.question_generator import generate_question
from app.ai.response_evaluator import evaluate_response, analyze_skill_gaps, generate_interview_summary, is_no_answer
from app.ai.adaptive_engine import AdaptiveEngine
from app.services.speech_service import SpeechAnalyzer
from app.services.cv_service import CVAnalysisService
from app.models.interview import InterviewPhase

P = F = 0
ERRORS = []

def check(section, name, condition, detail=""):
    global P, F
    if condition:
        P += 1
        print(f"    ✅ {name}")
    else:
        F += 1
        msg = f"    ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        ERRORS.append(f"[{section}] {msg.strip()}")


async def run():
    # ════════════════════════════════════════════════════
    print("\n" + "=" * 65)
    print("  📄 TEST 1: RESUME PARSING")
    print("=" * 65)
    # ════════════════════════════════════════════════════

    # Create a real PDF
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    import io

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4).build([
        Paragraph("Vikky Developer - Senior Software Engineer", getSampleStyleSheet()["Normal"]),
        Paragraph("Python, FastAPI, React, PostgreSQL, Docker", getSampleStyleSheet()["Normal"]),
        Paragraph("TechCorp Inc - Led backend team (2021-2024)", getSampleStyleSheet()["Normal"]),
    ])
    pdf_bytes = buf.getvalue()
    print(f"    Created PDF: {len(pdf_bytes)} bytes")

    CALL_LOG.clear()
    raw_text, parsed = await parse_resume(pdf_bytes, "pdf")

    check("RESUME", "Raw text extracted", len(raw_text) > 10, f"got {len(raw_text)} chars")
    check("RESUME", "AI parser was called", any(c["matched"] == "RESUME_PARSE" for c in CALL_LOG))
    check("RESUME", f"Skills: {len(parsed.skills)} extracted", len(parsed.skills) == 5)
    
    skill_names = [s.name for s in parsed.skills]
    check("RESUME", "Python in skills", "Python" in skill_names)
    check("RESUME", "FastAPI in skills", "FastAPI" in skill_names)
    check("RESUME", "PostgreSQL in skills", "PostgreSQL" in skill_names)
    
    check("RESUME", "Skill has category", parsed.skills[0].category == "programming_language")
    check("RESUME", "Skill has proficiency", parsed.skills[0].proficiency == "advanced")
    check("RESUME", f"Projects: {len(parsed.projects)}", len(parsed.projects) == 1)
    check("RESUME", "Project has technologies", len(parsed.projects[0].technologies) > 0)
    check("RESUME", f"Experience: {len(parsed.experience)}", len(parsed.experience) == 1)
    check("RESUME", "Experience has company", parsed.experience[0].company == "TechCorp")
    check("RESUME", f"Education: {len(parsed.education)}", len(parsed.education) == 1)
    check("RESUME", "Has summary", parsed.summary is not None and len(parsed.summary) > 10)
    check("RESUME", f"Certifications: {len(parsed.certifications)}", len(parsed.certifications) == 1)
    check("RESUME", f"Research papers: {len(parsed.research_papers)}", len(parsed.research_papers) == 1)
    check("RESUME", f"Achievements: {len(parsed.achievements)}", len(parsed.achievements) == 1)

    print(f"\n    📊 Parsed: {len(parsed.skills)} skills, {len(parsed.projects)} projects, {len(parsed.experience)} exp, {len(parsed.education)} edu, {len(parsed.research_papers)} papers, {len(parsed.achievements)} achievements")
    print(f"    Summary: {parsed.summary}")

    # ════════════════════════════════════════════════════
    print("\n" + "=" * 65)
    print("  🎤 TEST 2: AI QUESTION GENERATION (All 5 Phases)")
    print("=" * 65)
    # ════════════════════════════════════════════════════

    resume_data = {
        "skills": [s.model_dump() for s in parsed.skills],
        "projects": [p.model_dump() for p in parsed.projects],
        "experience": [e.model_dump() for e in parsed.experience],
        "education": [e.model_dump() for e in parsed.education],
        "certifications": parsed.certifications,
        "research_papers": [r.model_dump() for r in parsed.research_papers],
        "achievements": parsed.achievements,
        "summary": parsed.summary,
    }

    phases_to_test = [
        (InterviewPhase.INTRODUCTION, "introduction"),
        (InterviewPhase.TECHNICAL, "technical"),
        (InterviewPhase.SYSTEM_DESIGN, "system_design"),
        (InterviewPhase.HR, "hr"),
    ]

    for phase, expected_match in phases_to_test:
        CALL_LOG.clear()
        q = await generate_question(
            phase=phase,
            target_role="Senior Backend Developer",
            difficulty=6.0,
            language="english",
            resume_data=resume_data,
            conversation_history=[],
        )
        
        matched = CALL_LOG[-1]["matched"] if CALL_LOG else "NONE"
        check("QUESTION", f"{phase.value}: AI called ({matched})", len(CALL_LOG) > 0)
        check("QUESTION", f"{phase.value}: has question text", len(q.get("question", "")) > 10)
        check("QUESTION", f"{phase.value}: has topic", "topic" in q)
        check("QUESTION", f"{phase.value}: has expected_keywords", "expected_keywords" in q)
        print(f"      → {q['question'][:80]}...")

    # Follow-up question
    CALL_LOG.clear()
    q_followup = await generate_question(
        phase=InterviewPhase.TECHNICAL,
        target_role="Senior Backend Developer",
        difficulty=7.0,
        language="english",
        resume_data=resume_data,
        conversation_history=[
            {"role": "interviewer", "content": "How does connection pooling work?"},
            {"role": "candidate", "content": "I used pgbouncer with asyncpg."},
        ],
        last_answer="I used pgbouncer with asyncpg.",
        last_question="How does connection pooling work?",
        needs_follow_up=True,
    )
    check("QUESTION", "Follow-up: generated", len(q_followup.get("question", "")) > 10)
    print(f"      → Follow-up: {q_followup['question'][:80]}...")

    # Unique / non-duplicate question verification
    CALL_LOG.clear()
    existing_qs = ["How does connection pooling work?", "Explain indices in PostgreSQL."]
    q_unique = await generate_question(
        phase=InterviewPhase.TECHNICAL,
        target_role="Senior Backend Developer",
        difficulty=7.0,
        language="english",
        resume_data=resume_data,
        conversation_history=[],
        existing_questions=existing_qs,
    )
    check("QUESTION", "Unique: generated", len(q_unique.get("question", "")) > 10)
    
    # Verify that existing_questions was included in the system prompt
    last_call = CALL_LOG[-1] if CALL_LOG else None
    has_existing_qs = False
    if last_call and "messages" in last_call:
        for msg in last_call["messages"]:
            if msg.get("role") == "system" and "How does connection pooling work?" in msg.get("content", ""):
                has_existing_qs = True
    check("QUESTION", "Unique: existing_questions passed to system prompt", has_existing_qs)
    print("      → Existing questions passed to system prompt successfully checked.")

    # ════════════════════════════════════════════════════
    print("\n" + "=" * 65)
    print("  🧠 TEST 3: AI ANSWER EVALUATION & SCORING")
    print("=" * 65)
    # ════════════════════════════════════════════════════

    CALL_LOG.clear()
    evaluation = await evaluate_response(
        question="How would you design connection pooling for 10K concurrent requests?",
        question_type="technical",
        expected_keywords=["pool", "pgbouncer", "async", "timeout"],
        difficulty=6.0,
        answer="I designed our connection pooling with asyncpg and pgbouncer. Pool size of 20 with max overflow 10. Used pool_recycle=300s and pool_pre_ping for health checks. Prepared statements for hot queries.",
    )

    eval_calls = [c for c in CALL_LOG if c["matched"] == "EVALUATE_RESPONSE"]
    check("EVAL", f"AI evaluator called ({len(eval_calls)} times)", len(eval_calls) == 1)
    check("EVAL", f"Score = {evaluation['score']} (expected 7.8)", evaluation["score"] == 7.8)
    check("EVAL", "Score in range [0, 10]", 0 <= evaluation["score"] <= 10)
    check("EVAL", f"Feedback length = {len(evaluation['feedback'])}", len(evaluation["feedback"]) > 30)
    check("EVAL", f"Strengths count = {len(evaluation['strengths'])}", len(evaluation["strengths"]) == 3)
    check("EVAL", f"Weaknesses count = {len(evaluation['weaknesses'])}", len(evaluation["weaknesses"]) == 2)
    check("EVAL", f"should_follow_up = {evaluation['should_follow_up']}", evaluation["should_follow_up"] == True)
    check("EVAL", f"difficulty_adjustment = {evaluation['difficulty_adjustment']}", evaluation["difficulty_adjustment"] == 1)
    check("EVAL", f"technical_accuracy = {evaluation.get('technical_accuracy')}", evaluation.get("technical_accuracy") == 8.5)
    check("EVAL", f"communication = {evaluation.get('communication')}", evaluation.get("communication") == 7.5)

    check("EVAL", "is_no_answer('') is True", is_no_answer("") == True)
    check("EVAL", "is_no_answer('(Silence)') is True", is_no_answer("(Silence)") == True)
    check("EVAL", "is_no_answer('I don\\'t know') is True", is_no_answer("I don't know") == True)
    check("EVAL", "is_no_answer('skip') is True", is_no_answer("skip") == True)

    no_ans_eval = await evaluate_response(
        question="Explain garbage collection in Java.",
        question_type="technical",
        expected_keywords=["gc", "heap"],
        difficulty=6.0,
        answer="(Silence)",
    )
    check("EVAL", f"No-answer score = {no_ans_eval['score']}", no_ans_eval["score"] == 0.0)
    check("EVAL", f"No-answer tech accuracy = {no_ans_eval['technical_accuracy']}", no_ans_eval["technical_accuracy"] == 0.0)

    print(f"\n    📊 Score: {evaluation['score']}/10")
    print(f"    Feedback: {evaluation['feedback'][:100]}...")
    print(f"    Strengths: {evaluation['strengths']}")
    print(f"    Weaknesses: {evaluation['weaknesses']}")

    # ── Adaptive Difficulty ──
    print("\n    --- Adaptive Difficulty Engine ---")
    engine = AdaptiveEngine(initial_difficulty=5.0)
    
    # Strong answers → difficulty increases
    engine.update(evaluation["score"], evaluation["difficulty_adjustment"])
    engine.update(8.0, 1)
    engine.update(8.5, 1)
    check("ADAPTIVE", f"After strong answers: {engine.current_difficulty} > 5.0", engine.current_difficulty > 5.0)
    
    # Weak answers → difficulty decreases
    engine2 = AdaptiveEngine(initial_difficulty=5.0)
    engine2.update(2.0, -1)
    engine2.update(2.5, -1)
    engine2.update(1.5, -1)
    check("ADAPTIVE", f"After weak answers: {engine2.current_difficulty} < 5.0", engine2.current_difficulty < 5.0)
    check("ADAPTIVE", "Hint needed after 2 low scores", engine2.get_hint_needed())

    # ── Speech Analysis ──
    print("\n    --- Speech Analysis ---")
    sa = SpeechAnalyzer()
    speech = sa.analyze_transcript(
        "I designed our connection pooling strategy using asyncpg with SQLAlchemy. "
        "We um configured a pool size of twenty with um max overflow of ten. "
        "I used like pgbouncer as a connection multiplexer between the app and database.",
        duration_seconds=45.0,
    )
    check("SPEECH", f"WPM = {speech['wpm']}", speech["wpm"] > 0)
    check("SPEECH", f"Filler count = {speech['filler_word_count']}", speech["filler_word_count"] >= 3)
    check("SPEECH", f"Overall score = {speech['scores']['overall']}", speech["scores"]["overall"] > 0)
    check("SPEECH", f"Coaching tips = {len(speech['coaching'])}", len(speech["coaching"]) > 0)

    # ── CV Analysis ──
    print("\n    --- CV Analysis (Fallback Mode) ---")
    import base64
    cv = CVAnalysisService()
    for _ in range(10):
        cv.analyze_frame_base64(base64.b64encode(b"fake-frame").decode())
    summary = cv.get_session_summary()
    check("CV", f"Frames analyzed = {summary['total_frames_analyzed']}", summary["total_frames_analyzed"] == 10)
    check("CV", f"Avg confidence = {summary['avg_confidence']}", summary["avg_confidence"] > 0)
    check("CV", f"Dominant emotion = {summary['dominant_emotion']}", summary["dominant_emotion"] == "neutral")

    # ── Skill Gap Analysis ──
    print("\n    --- Skill Gap Analysis ---")
    CALL_LOG.clear()
    gaps = await analyze_skill_gaps(
        target_role="Senior Backend Developer",
        skills=[{"name": "Python", "proficiency": "advanced"}, {"name": "FastAPI", "proficiency": "advanced"}],
        performance={"average_score": 7.5, "total_questions": 5},
    )
    gap_calls = [c for c in CALL_LOG if c["matched"] == "SKILL_GAP"]
    check("GAPS", "AI skill gap analyzer called", len(gap_calls) == 1)
    check("GAPS", "Has matching_skills", len(gaps.get("matching_skills", [])) > 0)
    check("GAPS", "Has missing_skills", len(gaps.get("missing_skills", [])) > 0)
    check("GAPS", "Has improvement_roadmap", len(gaps.get("improvement_roadmap", [])) > 0)
    check("GAPS", f"Overall readiness = {gaps.get('overall_readiness')}", gaps.get("overall_readiness") == 68)

    # ── Interview Summary ──
    print("\n    --- Interview Summary ---")
    CALL_LOG.clear()
    summary_result = await generate_interview_summary(
        candidate_name="Vikky",
        target_role="Senior Backend Developer",
        question_scores=[{"question": "Q1", "score": 7.8, "feedback": "Good"}],
        avg_technical=7.8,
        avg_communication=7.5,
        speech_metrics=speech,
        anti_cheat_flags=None,
    )
    sum_calls = [c for c in CALL_LOG if c["matched"] == "INTERVIEW_SUMMARY"]
    check("SUMMARY", "AI summary generator called", len(sum_calls) == 1)
    check("SUMMARY", "Has summary text", len(summary_result.get("summary", "")) > 10)
    check("SUMMARY", "Has top_strengths", len(summary_result.get("top_strengths", [])) > 0)
    check("SUMMARY", "Has hire_recommendation", summary_result.get("hire_recommendation") == "yes")

    # ════════════════════════════════════════════════════
    print("\n" + "=" * 65)
    print("  🔍 COMPLETE AI CALL LOG")
    print("=" * 65)
    all_matches = {}
    for c in CALL_LOG:
        m = c["matched"]
        all_matches[m] = all_matches.get(m, 0) + 1
    for m, count in sorted(all_matches.items()):
        print(f"    • {m}: {count} call(s)")

    # ════════════════════════════════════════════════════
    total = P + F
    print("\n" + "=" * 65)
    if F == 0:
        print(f"  🎉 ALL {total} CHECKS PASSED!")
    else:
        print(f"  🏁 RESULTS: {P} passed, {F} failed out of {total}")
    print("=" * 65)
    if ERRORS:
        print("\n  Failures:")
        for e in ERRORS:
            print(f"    {e}")
    return F == 0


if __name__ == "__main__":
    success = asyncio.run(run())
    sys.exit(0 if success else 1)
