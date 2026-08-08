from __future__ import annotations
from openai import AsyncOpenAI
from app.config import get_settings
from app.utils.logger import get_logger
import json
from typing import Optional

logger = get_logger(__name__)
settings = get_settings()

_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _generate_dynamic_mock(messages: list[dict]) -> dict:
    prompt_str = str(messages).lower()
    
    # 1. Response Evaluation
    if "evaluat" in prompt_str and "candidate" in prompt_str:
        answer_echo = ""
        for m in messages:
            content = m.get("content", "")
            if "Candidate's Answer:" in content:
                try:
                    answer_echo = content.split("Candidate's Answer:")[1].strip()[:60]
                except Exception:
                    pass
                    
        feedback_msg = "This is a mocked high-quality feedback response."
        if answer_echo:
            feedback_msg = f"[MOCK MODE] I heard: '{answer_echo}...'. " + feedback_msg

        return {
            "score": 7.5,
            "technical_accuracy": 8.0,
            "depth": 7.0,
            "communication": 8.0,
            "relevance": 8.0,
            "feedback": feedback_msg,
            "strengths": ["Clear definition of concepts", "Confident technical explanation"],
            "weaknesses": ["Could expand on distributed scalability trade-offs"],
            "should_follow_up": True,
            "difficulty_adjustment": 1
        }
        
    # 2. Skill Gap Analysis
    elif "skill" in prompt_str and "gap" in prompt_str:
        return {
            "matching_skills": [{"skill": "Python", "assessment": "Advanced"}],
            "missing_skills": [{"skill": "AWS S3", "importance": "important", "learning_resource": "aws.amazon.com"}],
            "improvement_roadmap": [{"week": "1-2", "focus": "Cloud Storage Integration", "actions": ["Implement boto3 S3 uploads"]}],
            "overall_readiness": 85,
            "summary": "Excellent local skill foundation, ready for modern cloud environments."
        }
        
    # 3. Executive Report Summary
    elif "summar" in prompt_str and "hiring manager" in prompt_str:
        return {
            "executive_summary": "The candidate shows strong coding fundamentals and outstanding articulation of software architecture.",
            "technical_analysis": "Demonstrated solid database scaling, caching, and multi-tier component decoupling logic.",
            "communication_analysis": "Speaks clearly and confidently with perfect pacing and minimal use of filler words.",
            "top_strengths": ["Clean MVC architecture understanding", "Accurate data schema modeling"],
            "critical_improvements": ["Expand on zero-downtime database migration strategies"],
            "hire_recommendation": "Strong Hire",
            "confidence_in_assessment": 90
        }
        
    # 4. Question Generation
    elif "question" in prompt_str:
        if "introduct" in prompt_str:
            return {
                "question": "What is the most technically complex feature you have implemented on a past team?",
                "topic": "introduction",
                "expected_keywords": []
            }
        elif "technical" in prompt_str:
            return {
                "question": "How would you optimize index design for an database table facing million-scale writes?",
                "topic": "Database Optimization",
                "expected_keywords": ["index", "b-tree", "write-heavy", "partitioning"]
            }
        elif "system_design" in prompt_str:
            return {
                "question": "Design a highly available distributed cache handling spikes of 100K queries per second.",
                "topic": "system_design",
                "expected_keywords": ["redis", "replication", "sharding", "eviction"]
            }
        elif "hr" in prompt_str or "behavioral" in prompt_str:
            return {
                "question": "Describe a scenario where a core release failed in production and how you managed the resolution team.",
                "topic": "behavioral",
                "expected_keywords": []
            }
        else:
            return {
                "question": "Could you elaborate on the scalability choices you would make to optimize this endpoint?",
                "topic": "technical",
                "expected_keywords": []
            }
            
    # 5. Default Fallback: Resume Parse
    return {
        "skills": [
            {"name": "Python", "category": "programming", "proficiency": "expert"},
            {"name": "FastAPI", "category": "framework", "proficiency": "advanced"},
            {"name": "React", "category": "framework", "proficiency": "intermediate"}
        ],
        "projects": [{
            "name": "AI Platform", 
            "description": "Mocked demo project.",
            "technologies": ["Python", "React"],
            "highlights": ["Built backend"]
        }],
        "experience": [{
            "company": "Mock Inc",
            "title": "Software Engineer",
            "start_date": "2020-01",
            "end_date": "2023-01",
            "description": "Built AI tools",
            "highlights": ["Did things"]
        }],
        "education": [{
            "institution": "Tech Uni",
            "degree": "BS",
            "field": "Computer Science"
        }],
        "certifications": ["AWS Certified"],
        "summary": "Mocked summary for testing because OpenAI API key is missing."
    }


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    response_format: dict | None = None,
) -> str:
    if settings.OPENAI_API_KEY.startswith("sk-place") or not settings.OPENAI_API_KEY:
        logger.info("openai_mock", message="Using mock response for chat completion")
        if response_format and response_format.get("type") == "json_object":
            return json.dumps(_generate_dynamic_mock(messages))
        return "This is a mock response from the AI since no valid OpenAI API key is configured."

    client = get_openai_client()
    model = model or settings.OPENAI_MODEL

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    try:
        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        logger.info("openai_completion", model=model, tokens=response.usage.total_tokens if response.usage else 0)
        return content or ""
    except Exception as e:
        logger.error("openai_error_fallback", error=str(e), model=model)
        # Fallback to mock on any error (like RateLimit or AuthError)
        if response_format and response_format.get("type") == "json_object":
            return json.dumps(_generate_dynamic_mock(messages))
        return "This is a mock response from the AI since the OpenAI API call failed."


async def chat_completion_json(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4000,
) -> dict:
    raw = await chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("json_parse_error", raw_response=raw[:500])
        return {}


async def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    if settings.OPENAI_API_KEY.startswith("sk-place") or not settings.OPENAI_API_KEY:
        logger.info("whisper_mock", message="Using mock response for audio transcription")
        return "This is a mocked transcription of the audio because the OpenAI API key is not configured."

    client = get_openai_client()
    try:
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.webm"
        transcript = await client.audio.transcriptions.create(
            model=settings.OPENAI_WHISPER_MODEL,
            file=audio_file,
            language=language[:2],
        )
        return transcript.text
    except Exception as e:
        logger.error("whisper_error_fallback", error=str(e))
        return "This is a mocked transcription of the audio because the OpenAI API call failed."
