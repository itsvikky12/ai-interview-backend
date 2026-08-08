from __future__ import annotations
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.interview import Interview, InterviewStatus, InterviewPhase
from app.models.question import Question, QuestionType
from app.models.response import Response
from app.models.resume import Resume
from app.ai.question_generator import generate_question, generate_interview_path
from app.ai.response_evaluator import evaluate_response, is_no_answer
from app.ai.adaptive_engine import AdaptiveEngine
from app.utils.redis_client import RedisCache
from app.utils.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

PHASE_QUESTION_TYPES = {
    InterviewPhase.INTRODUCTION: QuestionType.INTRODUCTION,
    InterviewPhase.TECHNICAL: QuestionType.TECHNICAL,
    InterviewPhase.SYSTEM_DESIGN: QuestionType.SYSTEM_DESIGN,
    InterviewPhase.HR: QuestionType.HR,
}

PHASE_DURATIONS = {
    InterviewPhase.INTRODUCTION: settings.INTRO_MINUTES * 60,
    InterviewPhase.TECHNICAL: settings.TECHNICAL_MINUTES * 60,
    InterviewPhase.SYSTEM_DESIGN: settings.SYSTEM_DESIGN_MINUTES * 60,
    InterviewPhase.HR: settings.HR_MINUTES * 60,
}

PHASE_ORDER = [
    InterviewPhase.INTRODUCTION,
    InterviewPhase.TECHNICAL,
    InterviewPhase.SYSTEM_DESIGN,
    InterviewPhase.HR,
]

MANDATORY_QUESTIONS = [
    "Tell me about yourself."
]

FIRST_ROUND_QUESTIONS = [
    "Tell me about yourself.",
    "Take us through your resume.",
    "Why did you choose B.Tech/MCA?",
    "Why are you interested in this role?",
    "Why do you want to work with our company?",
    "What do you know about our company and its products/services?",
    "Which subjects did you enjoy the most during your course and why?",
    "Tell us about your final-year project or a project you are proud of.",
    "Have you completed any internships, certifications, or online courses? What did you learn?",
    "What are your biggest strengths?",
    "What is one area where you are currently working to improve?",
    "Why should we hire you over other fresh graduates?",
    "What motivates you to perform your best?",
    "What are your short-term and long-term career goals?",
    "Where do you see yourself in the next 3–5 years?",
    "What does success mean to you?",
    "What has been your biggest achievement as a student?",
    "Tell me about a challenge you faced during your academics or project and how you handled it.",
    "Describe a situation where things did not go as planned. What did you learn?",
    "How do you handle pressure during exams, project deadlines, or placements?",
    "How do you prioritize multiple assignments or deadlines?",
    "What kind of work environment helps you perform your best?",
    "How do you respond when someone gives you constructive feedback?",
    "Tell us about a mistake you made during a project or assignment. What did you learn?",
    "Have you ever taken the lead in a college project or event?",
    "Do you enjoy working independently or in a team? Why?",
    "Tell us about a team project where you contributed significantly.",
    "How would your classmates describe you?",
    "How do you manage your time during a busy semester?",
    "What are your hobbies or interests outside academics?",
    "Which technical skill have you learned on your own recently?",
    "Tell us about a time when you exceeded your own expectations.",
    "How do you handle tight deadlines?",
    "Tell us about a failure or setback and what it taught you.",
    "Which college experience has prepared you the most for this role?",
    "What type of mentor or manager would help you grow?",
    "How do you adapt when you have to learn a new technology quickly?",
    "Are you willing to relocate if required?",
    "Are you comfortable traveling for work if needed?",
    "What are your expectations from your first job?",
    "What qualities do you expect in your manager?",
    "What kind of company culture do you prefer?",
    "What makes you different from other candidates?",
    "How do you balance academics, extracurricular activities, and personal commitments?",
    "If selected, what would you aim to achieve during your first six months?",
    "Do you have any questions for us?",
    "Is there anything else you would like us to know about you?"
]


THIRD_ROUND_QUESTIONS = [
    "What inspired you to pursue your current field of study?",
    "Describe yourself in three words.",
    "Which personal values guide your decisions?",
    "What does a positive workplace look like to you?",
    "What does professional growth mean to you?",
    "What achievement outside academics are you most proud of?",
    "How do you react when plans change unexpectedly?",
    "What type of work excites you the most?",
    "What type of tasks do you enjoy the least, and how do you stay motivated?",
    "What factors are most important to your job satisfaction?",
    "Tell us about a time you helped a classmate or teammate.",
    "Describe a situation where you had to learn a new concept or technology quickly.",
    "What would you do if you disagreed with your team lead or manager?",
    "How do you build relationships with new teammates?",
    "What role do you usually take during group projects?",
    "How do you stay productive during repetitive or routine tasks?",
    "Tell us about a time when your work was appreciated.",
    "What is the best piece of advice you have ever received?",
    "What is the most valuable lesson you learned during college?",
    "How do you deal with uncertainty or unfamiliar situations?",
    "How would you describe your communication style?",
    "Besides salary, what are you looking for in your first employer?",
    "Have you ever missed a deadline? What happened, and what did you learn?",
    "How do you manage competing academic or project priorities?",
    "What type of recognition motivates you?",
    "How do you ensure quality in your work?",
    "Tell us about a time when you took initiative without being asked.",
    "What does teamwork mean to you?",
    "How do you approach solving a difficult problem?",
    "Which skill are you currently developing, and why?",
    "How do you prepare for an important presentation or interview?",
    "What would your friends say is your greatest strength?",
    "How do you maintain a healthy balance between academics and personal life?",
    "What does professionalism mean to you as a fresher?",
    "How do you react when someone points out your mistakes?",
    "What are your learning goals during your first year in the industry?",
    "Tell us about a difficult decision you made during college.",
    "How do you handle situations where the requirements are unclear?",
    "What kind of projects would you like to work on?",
    "Have you ever volunteered for responsibilities beyond your assigned role?",
    "What makes you feel valued in a team?",
    "Tell us about a time when you convinced someone to accept your idea.",
    "How do you stay focused on long-term goals?",
    "What would you do if you noticed a teammate struggling with a task?",
    "How do you evaluate your own performance?",
    "What is the most challenging feedback you have received?",
    "How do you stay positive during setbacks?",
    "If you could improve one thing about your college experience, what would it be?",
    "Which qualities do you admire most in successful professionals?",
    "If selected, how soon can you join our organization?"
]


class InterviewService:
    def __init__(self, db: AsyncSession, cache: RedisCache):
        self.db = db
        self.cache = cache

    async def _commit_db(self) -> None:
        import inspect
        res = self.db.commit()
        if inspect.isawaitable(res):
            await res

    def _build_resume_data_dict(self, resume: Resume) -> dict:
        return {
            "skills": resume.skills,
            "projects": resume.projects,
            "experience": resume.experience,
            "education": resume.education,
            "certifications": resume.certifications,
            "research_papers": resume.research_papers,
            "achievements": resume.achievements,
            "summary": resume.summary,
        }

    async def create_interview(self, user_id: UUID, target_role: str, resume_id: UUID | None, language: str) -> Interview:
        resume_data = None
        if resume_id:
            result = await self.db.execute(select(Resume).where(Resume.id == str(resume_id), Resume.user_id == str(user_id)))
            resume = result.scalar_one_or_none()
            if resume:
                resume_data = self._build_resume_data_dict(resume)
        else:
            result = await self.db.execute(
                select(Resume).where(Resume.user_id == str(user_id), Resume.is_primary == True)
            )
            resume = result.scalar_one_or_none()
            if resume:
                resume_id = resume.id
                resume_data = self._build_resume_data_dict(resume)

        interview = Interview(
            user_id=str(user_id),
            resume_id=str(resume_id) if resume_id else None,
            target_role=target_role,
            language=language,
            status=InterviewStatus.SCHEDULED,
        )
        self.db.add(interview)
        await self.db.flush()
        await self.db.refresh(interview)
        await self._commit_db()

        # Initialize state in Redis
        engine = AdaptiveEngine(initial_difficulty=7.0)
        state = {
            "phase": InterviewPhase.INTRODUCTION.value,
            "question_index": 0,
            "adaptive_engine": engine.to_dict(),
            "resume_data": resume_data,
            "phase_start_time": None,
            "last_question_id": None,
        }
        await self.cache.set_interview_state(str(interview.id), state)

        logger.info("interview_created", interview_id=str(interview.id), target_role=target_role)
        return interview

    async def start_interview(self, interview_id: UUID, user_id: UUID) -> dict:
        interview = await self._get_interview(interview_id, user_id)
        if interview.status != InterviewStatus.SCHEDULED:
            if interview.status == InterviewStatus.IN_PROGRESS:
                result = await self.db.execute(
                    select(Question)
                    .where(Question.interview_id == str(interview_id))
                    .order_by(Question.order_index, Question.expected_keywords.desc(), Question.created_at.desc())
                )
                raw_questions = result.scalars().all()
                seen_indices = set()
                questions = []
                for q in raw_questions:
                    if q.order_index not in seen_indices:
                        seen_indices.add(q.order_index)
                        questions.append(q)
                questions_data = [
                    {
                        "id": str(q.id),
                        "question_text": q.question_text,
                        "question_type": q.question_type.value,
                        "difficulty": q.difficulty,
                        "topic": q.topic,
                        "order_index": q.order_index,
                    }
                    for q in questions
                ]
                
                # Fetch all fallbacks just to make sure we have cached all 20 preloaded
                if len(questions_data) < 20:
                    for i in range(len(questions_data), 20):
                        q_data = await self._get_pregenerated_question(interview_id, i)
                        if q_data:
                            questions_data.append(q_data)
                            
                state = await self.get_or_restore_interview_state(interview_id, user_id)
                curr_idx = state.get("question_index", 0)
                return {
                    "interview_id": str(interview.id),
                    "phase": interview.current_phase.value,
                    "question": questions_data[curr_idx] if curr_idx < len(questions_data) else (questions_data[-1] if questions_data else None),
                    "questions": questions_data,
                    "time_remaining": 60,
                }
            raise HTTPException(status_code=400, detail="Interview already completed")

        interview.status = InterviewStatus.IN_PROGRESS
        interview.started_at = datetime.now(timezone.utc)
        interview.current_phase = InterviewPhase.INTRODUCTION
        await self.db.flush()

        state = await self.get_or_restore_interview_state(interview_id, user_id)
        state["phase_start_time"] = datetime.now(timezone.utc).isoformat()
        state["question_index"] = 0

        # Select 5 first round questions
        # First question is always "Tell me about yourself."
        selected_questions = ["Tell me about yourself."]
        import random
        # Sample 4 unique questions from the other 49 questions
        other_questions = random.sample(FIRST_ROUND_QUESTIONS[1:], 4)
        selected_questions.extend(other_questions)

        # Insert all 5 introduction questions synchronously
        for i, q_text in enumerate(selected_questions):
            db_q = Question(
                interview_id=str(interview.id),
                question_text=q_text,
                question_type=QuestionType.INTRODUCTION,
                difficulty=5.0,
                order_index=i,
                topic="Introduction",
                expected_keywords="first_round_mandatory" if i == 0 else "",
            )
            self.db.add(db_q)

        # Select 5 third round (HR) questions
        hr_questions = random.sample(THIRD_ROUND_QUESTIONS, 5)
        for i, q_text in enumerate(hr_questions):
            db_q = Question(
                interview_id=str(interview.id),
                question_text=q_text,
                question_type=QuestionType.HR,
                difficulty=7.0,
                order_index=15 + i,
                topic="HR Round",
                expected_keywords="third_round_mandatory",
            )
            self.db.add(db_q)
        
        await self._commit_db()
        await self.cache.set_interview_state(str(interview_id), state)

        # Kick off background preloading task for Question 2 and Question 3!
        import asyncio
        asyncio.create_task(self.preload_next_questions_task(interview_id, user_id, 0))

        # Retrieve all pre-generated questions sorted by order_index
        questions_data = []
        for i in range(5):
            q_data = await self._get_pregenerated_question(interview_id, i)
            if q_data:
                questions_data.append(q_data)

        # Fill with fallbacks to ensure client instantly has the cached array of 20 questions!
        for i in range(5, 20):
            fb_data = await self._get_pregenerated_question(interview_id, i)
            if fb_data:
                questions_data.append(fb_data)

        q1_data = questions_data[0] if questions_data else None

        return {
            "interview_id": str(interview.id),
            "phase": interview.current_phase.value,
            "question": q1_data,
            "questions": questions_data,
            "time_remaining": 60,
        }

    async def submit_answer(self, interview_id: UUID, user_id: UUID, question_id: UUID, answer_text: str, audio_url: str | None = None, duration_seconds: float | None = None) -> dict:
        interview = await self._get_interview(interview_id, user_id)
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Interview is not in progress")

        result = await self.db.execute(select(Question).where(Question.id == str(question_id), Question.interview_id == str(interview_id)))
        question = result.scalar_one_or_none()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        # Weak answer detection heuristic
        is_weak = False
        words = [w for w in answer_text.strip().lower().split() if w]
        word_count = len(words)
        
        # Checking short responses or pass/skip phrases
        refusals = {"don't know", "dont know", "no idea", "skip", "pass", "next", "i don't know", "i dont know", "no clue"}
        answer_normalized = " ".join(words)

        # Check for early exit command
        is_early_exit = answer_normalized.strip(" .!?") == "end interview"

        if is_early_exit:
            response = Response(
                interview_id=str(interview_id),
                question_id=str(question_id),
                answer_text=answer_text,
                audio_url=audio_url,
                score=0.0,
                feedback="Interview ended early by candidate.",
                strengths=[],
                weaknesses=["candidate_response_incomplete_flag", "early_exit"],
                wpm=None,
                duration_seconds=duration_seconds,
            )
            self.db.add(response)
            interview.total_questions += 1
            await self._complete_interview(interview)
            await self.db.flush()
            return {
                "question_id": str(question_id),
                "evaluation": {
                    "score": 0.0,
                    "feedback": "Interview ended early by candidate.",
                    "strengths": [],
                    "weaknesses": [],
                    "should_follow_up": False,
                    "difficulty_adjustment": 0,
                },
                "next_question": None,
                "phase": "completed",
                "interview_completed": True,
            }
        
        if word_count < 15 or is_no_answer(answer_text) or any(ref in answer_normalized for ref in refusals):
            is_weak = True

        weaknesses_list = ["candidate_response_incomplete_flag"] if is_weak else []

        # Save response immediately with raw text or base64 audio
        response = Response(
            interview_id=str(interview_id),
            question_id=str(question_id),
            answer_text=answer_text,
            audio_url=audio_url,
            score=0.0,
            feedback="Pending evaluation...",
            strengths=[],
            weaknesses=weaknesses_list,
            wpm=None,
            duration_seconds=duration_seconds,
        )
        self.db.add(response)
        interview.total_questions += 1

        # Kick off background evaluation task for this response immediately!
        import asyncio
        asyncio.create_task(evaluate_response_background(str(interview_id), str(question_id), answer_text, duration_seconds))

        # Store conversation message
        await self.cache.add_conversation_message(str(interview_id), {
            "role": "interviewer", "content": question.question_text
        })
        history_answer = "(Audio recording submitted)" if answer_text.startswith("__AUDIO__:") else answer_text
        await self.cache.add_conversation_message(str(interview_id), {
            "role": "candidate", "content": history_answer
        })

        # Increment question index
        state = await self.get_or_restore_interview_state(interview_id, user_id)
        state["question_index"] = state.get("question_index", 0) + 1
        state["last_question_id"] = str(question_id)

        # Check if candidate completed the 20 AI interview questions (5 Intro, 10 Technical, 5 HR)
        if state["question_index"] >= 20:
            interview.current_phase = InterviewPhase.CODING_ASSESSMENT
            state["phase"] = InterviewPhase.CODING_ASSESSMENT.value
            await self._commit_db()
            await self.cache.set_interview_state(str(interview_id), state)
            return {
                "question_id": str(question_id),
                "evaluation": {
                    "score": 0.0,
                    "feedback": "AI Interview questions completed! Proceeding to Online Coding Assessment.",
                    "strengths": [],
                    "weaknesses": [],
                    "should_follow_up": False,
                    "difficulty_adjustment": 0,
                },
                "next_question": None,
                "phase": "coding_assessment",
                "interview_completed": False,
                "redirect_to_coding": True,
            }

        # Otherwise fetch next pre-generated question
        next_question_data = await self._get_pregenerated_question(interview_id, state["question_index"])
        if not next_question_data:
            interview.current_phase = InterviewPhase.CODING_ASSESSMENT
            state["phase"] = InterviewPhase.CODING_ASSESSMENT.value
            await self._commit_db()
            await self.cache.set_interview_state(str(interview_id), state)
            return {
                "question_id": str(question_id),
                "evaluation": {
                    "score": 0.0,
                    "feedback": "AI Interview questions completed! Proceeding to Online Coding Assessment.",
                    "strengths": [],
                    "weaknesses": [],
                    "should_follow_up": False,
                    "difficulty_adjustment": 0,
                },
                "next_question": None,
                "phase": "coding_assessment",
                "interview_completed": False,
                "redirect_to_coding": True,
            }

        # Dynamically set new phase based on next question's order index (20 questions total)
        # 0-4: Introduction (5 q), 5-14: Technical (10 q), 15-19: HR (5 q)
        idx = state["question_index"]
        if idx >= 0 and idx <= 4:
            new_phase = InterviewPhase.INTRODUCTION
        elif idx >= 5 and idx <= 14:
            new_phase = InterviewPhase.TECHNICAL
        else:
            new_phase = InterviewPhase.HR

        interview.current_phase = new_phase
        state["phase"] = new_phase.value
        state["phase_start_time"] = datetime.now(timezone.utc).isoformat()

        await self.cache.set_interview_state(str(interview_id), state)
        await self._commit_db()

        # Kick off background preloading for the next sliding window!
        import asyncio
        asyncio.create_task(self.preload_next_questions_task(interview_id, user_id, state["question_index"]))

        return {
            "question_id": str(question_id),
            "evaluation": {
                "score": 0.0,
                "feedback": "Answer recorded.",
                "strengths": [],
                "weaknesses": [],
                "should_follow_up": False,
                "difficulty_adjustment": 0,
            },
            "next_question": next_question_data,
            "phase": new_phase.value,
            "difficulty": next_question_data.get("difficulty", 5.0),
            "interview_completed": False,
        }

    async def _get_pregenerated_question(self, interview_id: UUID, order_index: int) -> dict | None:
        result = await self.db.execute(
            select(Question)
            .where(
                Question.interview_id == str(interview_id),
                Question.order_index == order_index
            )
            .order_by(
                Question.expected_keywords.desc(),
                Question.created_at.desc()
            )
        )
        q = result.scalars().first()
        if not q:
            # High-quality fallback questions in case background preloading is still in progress
            FALLBACKS = {
                1: {
                    "text": "Which subjects did you enjoy the most during your course and why?",
                    "type": InterviewPhase.INTRODUCTION,
                    "topic": "Introduction",
                    "diff": 5.0,
                },
                2: {
                    "text": "What are your short-term and long-term career goals?",
                    "type": InterviewPhase.INTRODUCTION,
                    "topic": "Introduction",
                    "diff": 5.0,
                },
                3: {
                    "text": "What are your biggest strengths?",
                    "type": InterviewPhase.INTRODUCTION,
                    "topic": "Introduction",
                    "diff": 5.0,
                },
                4: {
                    "text": "Why should we hire you over other fresh graduates?",
                    "type": InterviewPhase.INTRODUCTION,
                    "topic": "Introduction",
                    "diff": 5.0,
                },
                5: {
                    "text": "Let's move to the Technical and Resume Round. Could you walk me through the architecture and technical choices behind your most significant project?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Project Discussion",
                    "diff": 6.0,
                },
                6: {
                    "text": "Based on the technologies listed in your profile, what is a highly complex technical challenge you faced while developing, and how did you resolve it?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Technical",
                    "diff": 6.4,
                },
                7: {
                    "text": "Imagine you are architecting a highly available, scalable system for a core feature in your domain. How would you approach database, caching, and load balancing tradeoffs?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Scenario-Based",
                    "diff": 6.8,
                },
                8: {
                    "text": "Let's look at problem solving. If a critical service under your ownership suddenly experiences a 10x spike in response times, walk me through your diagnostic and debugging process.",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Problem Solving",
                    "diff": 7.2,
                },
                9: {
                    "text": "Could you describe a real-world coding challenge you tackled recently? What was the complexity of your solution and how did you optimize it?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Real-World Implementation",
                    "diff": 7.6,
                },
                10: {
                    "text": "In your previous projects or experience, how did you ensure code quality, testing, and continuous integration/deployment (CI/CD) pipelines?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "CI/CD & Testing",
                    "diff": 8.0,
                },
                11: {
                    "text": "Explain how you handle state management, performance optimization, or caching in a web application or system you've built.",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Performance & State",
                    "diff": 8.4,
                },
                12: {
                    "text": "How do you secure your APIs and applications? Walk me through authentication, authorization, and data encryption techniques you have implemented.",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Security",
                    "diff": 8.8,
                },
                13: {
                    "text": "Describe a scenario where you had to refactor a large piece of legacy code. What was your strategy and how did you minimize regression risks?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Refactoring & Legacy",
                    "diff": 9.2,
                },
                14: {
                    "text": "How do you monitor and debug production systems? What tools or practices do you use for logging, alerting, and error tracking?",
                    "type": InterviewPhase.TECHNICAL,
                    "topic": "Monitoring & Debugging",
                    "diff": 9.6,
                },
                15: {
                    "text": "What inspired you to pursue your current field of study?",
                    "type": InterviewPhase.HR,
                    "topic": "HR Round",
                    "diff": 7.0,
                },
                16: {
                    "text": "What does professional growth mean to you?",
                    "type": InterviewPhase.HR,
                    "topic": "HR Round",
                    "diff": 7.0,
                },
                17: {
                    "text": "How do you manage competing academic or project priorities?",
                    "type": InterviewPhase.HR,
                    "topic": "HR Round",
                    "diff": 7.0,
                },
                18: {
                    "text": "What would you do if you disagreed with your team lead or manager?",
                    "type": InterviewPhase.HR,
                    "topic": "HR Round",
                    "diff": 7.0,
                },
                19: {
                    "text": "If selected, how soon can you join our organization?",
                    "type": InterviewPhase.HR,
                    "topic": "HR Round",
                    "diff": 7.0,
                }
            }
            fb = FALLBACKS.get(order_index)
            if not fb:
                return None
                
            fb_text = fb["text"]
            # Personalize technical fallback questions (index 5 to 14)
            if 5 <= order_index <= 14:
                skills_str = ""
                target_role = "Software Engineer"
                try:
                    int_result = await self.db.execute(select(Interview).where(Interview.id == str(interview_id)))
                    interview = int_result.scalar_one_or_none()
                    if interview:
                        target_role = interview.target_role
                        if interview.resume_id:
                            res_result = await self.db.execute(select(Resume).where(Resume.id == interview.resume_id))
                            resume = res_result.scalar_one_or_none()
                            if resume and resume.skills:
                                skills_list = [s["name"] if isinstance(s, dict) else str(s) for s in resume.skills[:5]]
                                if skills_list:
                                    skills_str = ", ".join(skills_list)
                except Exception as e:
                    logger.warning("fallback_personalization_lookup_failed", error=str(e))

                if not skills_str:
                    skills_str = target_role

                if order_index == 6:
                    fb_text = f"Based on your experience with {skills_str}, what is a highly complex technical challenge you faced while developing, and how did you resolve it?"
                elif order_index == 7:
                    fb_text = f"Imagine you are architecting a highly available, scalable system for a core feature using {skills_str}. How would you approach database, caching, and load balancing tradeoffs?"
                elif order_index == 8:
                    fb_text = f"Let's look at problem solving. If a critical service under your ownership using {skills_str} suddenly experiences a 10x spike in response times, walk me through your diagnostic and debugging process."
                elif order_index == 9:
                    fb_text = f"Could you describe a real-world coding challenge you tackled recently using {skills_str}? What was the complexity of your solution and how did you optimize it?"
                elif order_index == 10:
                    fb_text = f"In your projects involving {skills_str}, how did you ensure code quality, testing, and continuous integration/deployment (CI/CD) pipelines?"
                elif order_index == 11:
                    fb_text = f"Explain how you handle state management, performance optimization, or caching in a web application or system built with {skills_str}."
                elif order_index == 12:
                    fb_text = f"How do you secure your APIs and applications? Walk me through authentication, authorization, and data encryption techniques you have implemented in {skills_str}."
                elif order_index == 13:
                    fb_text = f"Describe a scenario where you had to refactor a large piece of code using {skills_str}. What was your strategy and how did you minimize regression risks?"
                elif order_index == 14:
                    fb_text = f"How do you monitor and debug production systems using {skills_str}? What tools or practices do you use for logging, alerting, and error tracking?"
                elif order_index == 15:
                    fb_text = f"What are some strategies for optimizing database queries or data access in a high-traffic application using {skills_str}?"
                elif order_index == 16:
                    fb_text = f"Can you explain how containerization and orchestration tools like Docker and Kubernetes work together for deploying a {skills_str} application?"
                elif order_index == 17:
                    fb_text = f"What is the difference between monolithic and microservices architectures? When would you choose one over the other for a project using {skills_str}?"
                elif order_index == 18:
                    fb_text = f"How do you handle asynchronous tasks and background processing in your applications using {skills_str}?"
                elif order_index == 19:
                    fb_text = f"Describe the principles of Continuous Integration and Continuous Deployment (CI/CD) for a {skills_str} project."

            db_q = Question(
                interview_id=str(interview_id),
                question_text=fb_text,
                question_type=fb["type"],
                difficulty=fb["diff"],
                order_index=order_index,
                topic=fb["topic"],
                expected_keywords=""
            )
            self.db.add(db_q)
            await self.db.flush()
            q = db_q

        return {
            "id": str(q.id),
            "question_text": q.question_text,
            "question_type": q.question_type.value,
            "difficulty": q.difficulty,
            "topic": q.topic,
            "order_index": q.order_index,
        }

    async def preload_next_questions_task(self, interview_id: UUID, user_id: UUID, current_index: int) -> None:
        from app.database import async_session
        from app.utils.redis_client import get_redis, RedisCache
        try:
            async with async_session() as db:
                cache = RedisCache(await get_redis())
                bg_service = InterviewService(db, cache)
                await bg_service._generate_and_save_next_questions(interview_id, user_id, current_index)
        except Exception as e:
            logger.error("preload_task_failed", error=str(e), interview_id=str(interview_id))

    async def _generate_and_save_next_questions(self, interview_id: UUID, user_id: UUID, current_index: int) -> None:
        interview = await self._get_interview(interview_id, user_id)
        state = await self.get_or_restore_interview_state(interview_id, user_id)
        
        target_indices = []
        if current_index == 0:
            target_indices = [1, 2]
        elif current_index in range(1, 18):
            target_indices = [current_index + 2]
            
        for idx in target_indices:
            if idx > 24:
                continue
            if idx <= 0 or idx >= 20:
                # Tell me about yourself (index 0) and HR round questions are pre-generated, no need to generate
                continue
                
            result = await self.db.execute(
                select(Question)
                .where(
                    Question.interview_id == str(interview_id),
                    Question.order_index == idx
                )
                .order_by(
                    Question.expected_keywords.desc(),
                    Question.created_at.desc()
                )
            )
            existing_q = result.scalars().first()
            
            # Map stages to phases and difficulties
            if idx >= 1 and idx <= 4:
                phase = InterviewPhase.INTRODUCTION
                topic = "Introduction"
                diff = 5.0
            elif idx >= 5 and idx <= 19:
                phase = InterviewPhase.TECHNICAL
                topic = "Technical"
                diff = 6.0 + (idx - 5) * 0.4
            else:
                phase = InterviewPhase.HR
                topic = "HR Round"
                diff = 7.0
                
            history = await self.cache.get_conversation_history(str(interview_id))
            
            existing_questions_res = await self.db.execute(
                select(Question.question_text).where(Question.interview_id == str(interview_id))
            )
            existing_questions = [q_text for (q_text,) in existing_questions_res.all() if q_text]

            q_data = await generate_question(
                phase=phase,
                target_role=interview.target_role,
                difficulty=diff,
                language=interview.language,
                resume_data=state.get("resume_data"),
                conversation_history=history,
                existing_questions=existing_questions
            )
            
            q_text = q_data.get("question", "Could you tell me more about your engineering experience?")
            keywords = ",".join(q_data.get("expected_keywords", [])) if isinstance(q_data.get("expected_keywords"), list) else ""
            
            if existing_q:
                # Overwrite if it was a fallback question (empty keywords) to give candidate the adaptive customized version!
                if existing_q.expected_keywords == "":
                    existing_q.question_text = q_text
                    existing_q.expected_keywords = keywords
                    self.db.add(existing_q)
                    await self.db.flush()
            else:
                db_q = Question(
                    interview_id=str(interview_id),
                    question_text=q_text,
                    question_type=phase,
                    difficulty=diff,
                    order_index=idx,
                    topic=topic,
                    expected_keywords=keywords
                )
                self.db.add(db_q)
                await self.db.flush()
                
        await self._commit_db()

    async def get_interview(self, interview_id: UUID, user_id: UUID) -> Interview:
        return await self._get_interview(interview_id, user_id)

    async def associate_resume(self, interview_id: UUID, user_id: UUID, resume_id: UUID) -> Interview:
        interview = await self._get_interview(interview_id, user_id)
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Interview is not in progress")

        result = await self.db.execute(select(Resume).where(Resume.id == str(resume_id), Resume.user_id == str(user_id)))
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        interview.resume_id = str(resume_id)
        
        resume_data = self._build_resume_data_dict(resume)

        # Update Redis state
        state = await self.get_or_restore_interview_state(interview_id, user_id)
        state["resume_data"] = resume_data
        await self.cache.set_interview_state(str(interview_id), state)

        # Force-generate personalized version for index 5 (first technical question)
        try:
            history = await self.cache.get_conversation_history(str(interview_id))
            existing_questions_res = await self.db.execute(
                select(Question.question_text).where(Question.interview_id == str(interview_id))
            )
            existing_questions = [q_text for (q_text,) in existing_questions_res.all() if q_text]

            q_data = await generate_question(
                phase=InterviewPhase.TECHNICAL,
                target_role=interview.target_role,
                difficulty=6.0,
                language=interview.language,
                resume_data=resume_data,
                conversation_history=history,
                existing_questions=existing_questions
            )
            q_text = q_data.get("question", "Could you walk me through the architecture and technical choices behind your most significant project?")
            keywords = ",".join(q_data.get("expected_keywords", [])) if isinstance(q_data.get("expected_keywords"), list) else ""
            
            result = await self.db.execute(
                select(Question)
                .where(
                    Question.interview_id == str(interview_id),
                    Question.order_index == 5
                )
                .order_by(
                    Question.expected_keywords.desc(),
                    Question.created_at.desc()
                )
            )
            q5 = result.scalars().first()
            if q5:
                q5.question_text = q_text
                q5.expected_keywords = keywords
                self.db.add(q5)
                await self.db.flush()
        except Exception as e:
            logger.error("associate_resume_personalization_q5_failed", error=str(e), interview_id=str(interview_id))

        await self.db.flush()
        await self._commit_db()

        # Kick off background preloading for the subsequent sliding window starting from index 4 (generates 6, 7, etc.)
        import asyncio
        asyncio.create_task(self.preload_next_questions_task(interview_id, user_id, 4))
        return interview

    async def get_user_interviews(self, user_id: UUID, skip: int = 0, limit: int = 20) -> list[Interview]:
        result = await self.db.execute(
            select(Interview)
            .where(Interview.user_id == str(user_id))
            .order_by(Interview.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def _get_interview(self, interview_id: UUID | str, user_id: UUID | str | None = None) -> Interview:
        stmt = select(Interview).where(Interview.id == str(interview_id))
        if user_id is not None:
            stmt = stmt.where(Interview.user_id == str(user_id))
        result = await self.db.execute(stmt)
        interview = result.scalar_one_or_none()
        
        if not interview and user_id is not None:
            # Fallback lookup by interview_id alone for cross-user or admin requests
            any_res = await self.db.execute(select(Interview).where(Interview.id == str(interview_id)))
            interview = any_res.scalar_one_or_none()

        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        return interview

    async def get_or_restore_interview_state(self, interview_id: UUID, user_id: UUID | None = None) -> dict:
        state = await self.cache.get_interview_state(str(interview_id))
        if state is not None:
            return state

        # Reconstruct state from DB
        if user_id is not None:
            interview = await self._get_interview(interview_id, user_id)
        else:
            result = await self.db.execute(
                select(Interview).where(Interview.id == str(interview_id))
            )
            interview = result.scalar_one_or_none()
            if not interview:
                raise HTTPException(status_code=404, detail="Interview not found")

        # Load resume data if present
        resume_data = None
        if interview.resume_id:
            result = await self.db.execute(select(Resume).where(Resume.id == interview.resume_id))
            resume = result.scalar_one_or_none()
            if resume:
                resume_data = self._build_resume_data_dict(resume)

        # Calculate current question_index based on count of existing responses
        resp_result = await self.db.execute(
            select(Response).where(Response.interview_id == str(interview_id))
        )
        responses = resp_result.scalars().all()
        question_index = len(responses)

        # Get last_question_id from the last response if it exists
        last_question_id = None
        if responses:
            sorted_responses = sorted(responses, key=lambda r: r.created_at)
            last_question_id = sorted_responses[-1].question_id

        # Reconstruct adaptive engine difficulty and score history
        scores = [r.score for r in responses if r.score is not None]
        engine = AdaptiveEngine(initial_difficulty=interview.difficulty_level or 7.0)
        engine.score_history = scores

        # Build restored state
        state = {
            "phase": interview.current_phase.value,
            "question_index": question_index,
            "adaptive_engine": engine.to_dict(),
            "resume_data": resume_data,
            "phase_start_time": (
                interview.started_at.isoformat()
                if interview.started_at
                else datetime.now(timezone.utc).isoformat()
            ),
            "last_question_id": last_question_id,
        }

        # Save back to cache
        await self.cache.set_interview_state(str(interview_id), state)
        logger.info("interview_state_restored", interview_id=str(interview_id), state=state)
        return state

    async def _generate_and_store_question(self, interview: Interview, state: dict, needs_follow_up: bool = False, last_answer: str | None = None, last_question: str | None = None) -> dict:
        phase = InterviewPhase(state["phase"])
        engine = AdaptiveEngine.from_dict(state.get("adaptive_engine", {}))
        conversation = await self.cache.get_conversation_history(str(interview.id))

        hint_text = ""
        if engine.get_hint_needed():
            hint_text = " (The candidate is struggling. Provide a simpler question or include a hint.)"

        existing_questions_res = await self.db.execute(
            select(Question.question_text).where(Question.interview_id == str(interview.id))
        )
        existing_questions = [q_text for (q_text,) in existing_questions_res.all() if q_text]

        q_data = await generate_question(
            phase=phase,
            target_role=interview.target_role + hint_text,
            difficulty=engine.current_difficulty,
            language=interview.language,
            resume_data=state.get("resume_data"),
            conversation_history=conversation,
            existing_questions=existing_questions,
            last_answer=last_answer,
            last_question=last_question,
            needs_follow_up=needs_follow_up,
        )

        question_type = PHASE_QUESTION_TYPES.get(phase, QuestionType.TECHNICAL)
        if needs_follow_up:
            question_type = QuestionType.FOLLOW_UP

        question = Question(
            interview_id=interview.id,
            question_text=q_data["question"],
            question_type=question_type,
            difficulty=engine.current_difficulty,
            order_index=state.get("question_index", 0),
            topic=q_data.get("topic"),
            expected_keywords=",".join(q_data.get("expected_keywords", [])),
        )
        self.db.add(question)
        await self.db.flush()
        await self.db.refresh(question)

        return {
            "id": str(question.id),
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "difficulty": question.difficulty,
            "topic": question.topic,
            "order_index": question.order_index,
        }

    async def _advance_phase(self, interview: Interview, state: dict) -> bool:
        current = InterviewPhase(state["phase"])
        current_idx = PHASE_ORDER.index(current) if current in PHASE_ORDER else -1
        next_idx = current_idx + 1

        if next_idx >= len(PHASE_ORDER):
            return False

        next_phase = PHASE_ORDER[next_idx]
        interview.current_phase = next_phase
        state["phase"] = next_phase.value
        state["phase_start_time"] = datetime.now(timezone.utc).isoformat()
        await self.cache.set_interview_state(str(interview.id), state)

        logger.info("phase_advanced", interview_id=str(interview.id), new_phase=next_phase.value)
        return True

    async def _complete_interview(self, interview: Interview) -> None:
        interview.status = InterviewStatus.COMPLETED
        interview.completed_at = datetime.now(timezone.utc)
        interview.current_phase = InterviewPhase.COMPLETED
        logger.info("interview_completed", interview_id=str(interview.id))

    def _get_phase_elapsed(self, state: dict) -> float:
        start_str = state.get("phase_start_time")
        if not start_str:
            return 0
        start = datetime.fromisoformat(start_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - start).total_seconds()


async def evaluate_response_background(
    interview_id: str,
    question_id: str,
    answer_text: str,
    duration_seconds: float | None = None
) -> None:
    """Evaluates the candidate response in the background and broadcasts the result via WebSocket."""
    import asyncio
    import base64
    from app.database import async_session
    from app.models.question import Question
    from app.models.response import Response
    from app.ai.openai_client import transcribe_audio
    from app.ai.response_evaluator import evaluate_response
    from app.utils.logger import get_logger

    logger = get_logger(__name__)

    try:
        # Retry loop to wait for response to be committed by the main thread
        response_committed = False
        for _ in range(6):
            async with async_session() as db:
                result = await db.execute(
                    select(Response).where(Response.question_id == question_id)
                )
                res_row = result.scalar_one_or_none()
                if res_row:
                    response_committed = True
                    break
            await asyncio.sleep(0.5)

        if not response_committed:
            logger.error("background_eval_response_not_committed_timeout", question_id=question_id)
            return

        # 1. Fetch the question details
        async with async_session() as db:
            result = await db.execute(
                select(Question).where(Question.id == question_id)
            )
            question = result.scalar_one_or_none()
            if not question:
                logger.error("background_eval_question_not_found", question_id=question_id)
                return
            
            question_text = question.question_text
            question_type = question.question_type.value
            expected_keywords = question.expected_keywords.split(",") if question.expected_keywords else []
            difficulty = question.difficulty

        # 2. Transcribe audio if needed
        final_answer = answer_text
        if final_answer.startswith("__AUDIO__:"):
            try:
                audio_b64 = final_answer.split("__AUDIO__:")[1]
                audio_bytes = base64.b64decode(audio_b64)
                transcription = await transcribe_audio(audio_bytes)
                final_answer = transcription if transcription.strip() else "(Silence)"
            except Exception as ex:
                logger.error("background_transcribe_failed", error=str(ex))
                final_answer = "(Failed to transcribe audio)"

        # Update Redis history so the model knows what the candidate actually said for future questions
        if answer_text.startswith("__AUDIO__:"):
            from app.utils.redis_client import get_redis, RedisCache
            cache = RedisCache(await get_redis())
            await cache.update_last_audio_message(interview_id, final_answer)

        # 3. Call OpenAI for evaluation
        evaluation = await evaluate_response(
            question=question_text,
            question_type=question_type,
            expected_keywords=expected_keywords,
            difficulty=difficulty,
            answer=final_answer,
        )

        # 4. Save results back to the database
        async with async_session() as db:
            result = await db.execute(
                select(Response).where(Response.question_id == question_id)
            )
            response = result.scalar_one_or_none()
            if response:
                response.answer_text = final_answer
                response.score = evaluation["score"]
                response.feedback = evaluation["feedback"]
                response.strengths = evaluation["strengths"]
                response.weaknesses = evaluation["weaknesses"]
                await db.commit()
            else:
                logger.error("background_eval_response_not_found", question_id=question_id)
                return

        # 5. Notify the active websocket connection (prevent circular import)
        try:
            from app.api.websocket.interview_ws import manager
            await manager.send(interview_id, {
                "type": "background_evaluation",
                "data": {
                    "question_id": question_id,
                    "evaluation": {
                        "score": evaluation["score"],
                        "feedback": evaluation["feedback"],
                        "strengths": evaluation["strengths"],
                        "weaknesses": evaluation["weaknesses"],
                        "should_follow_up": evaluation["should_follow_up"],
                        "communication": evaluation.get("communication", evaluation["score"]),
                    }
                }
            })
            logger.info("background_evaluation_broadcasted", interview_id=interview_id, question_id=question_id)
        except Exception as ws_ex:
            logger.error("background_eval_ws_notify_failed", error=str(ws_ex))

    except Exception as e:
        logger.error("background_eval_failed", error=str(e), question_id=question_id)
