import pytest
from app.ai.adaptive_engine import AdaptiveEngine
from app.services.speech_service import SpeechAnalyzer


class TestAdaptiveEngine:
    def test_initial_difficulty(self):
        engine = AdaptiveEngine(initial_difficulty=5.0)
        assert engine.current_difficulty == 5.0

    def test_clamps_to_range(self):
        engine = AdaptiveEngine(initial_difficulty=15.0)
        assert engine.current_difficulty == 10.0

        engine2 = AdaptiveEngine(initial_difficulty=-5.0)
        assert engine2.current_difficulty == 1.0

    def test_difficulty_increases_on_strong_answers(self):
        engine = AdaptiveEngine(initial_difficulty=5.0)
        # Three strong answers
        engine.update(8.5, 1)
        engine.update(9.0, 1)
        engine.update(8.0, 1)
        assert engine.current_difficulty > 5.0

    def test_difficulty_decreases_on_weak_answers(self):
        engine = AdaptiveEngine(initial_difficulty=7.0)
        engine.update(2.0, -1)
        engine.update(2.5, -1)
        engine.update(3.0, -1)
        assert engine.current_difficulty < 7.0

    def test_hint_needed_after_consecutive_low_scores(self):
        engine = AdaptiveEngine(initial_difficulty=5.0)
        engine.update(3.5, -1)
        engine.update(2.0, -1)
        assert engine.get_hint_needed() is True

    def test_no_hint_on_first_question(self):
        engine = AdaptiveEngine(initial_difficulty=5.0)
        assert engine.get_hint_needed() is False

    def test_serialization_roundtrip(self):
        engine = AdaptiveEngine(initial_difficulty=7.0)
        engine.update(8.0, 1)
        engine.update(6.0, 0)

        data = engine.to_dict()
        restored = AdaptiveEngine.from_dict(data)

        assert restored.current_difficulty == engine.current_difficulty
        assert restored.score_history == engine.score_history
        assert restored.average_score == engine.average_score

    def test_average_score(self):
        engine = AdaptiveEngine()
        engine.update(8.0, 1)
        engine.update(6.0, 0)
        engine.update(4.0, -1)
        assert engine.average_score == 6.0


class TestSpeechAnalyzer:
    def setup_method(self):
        self.analyzer = SpeechAnalyzer()

    def test_basic_analysis(self):
        transcript = "I have experience in Python and JavaScript. I worked on several web applications using React and Django frameworks."
        metrics = self.analyzer.analyze_transcript(transcript, duration_seconds=15.0)

        assert metrics["word_count"] > 0
        assert metrics["wpm"] > 0
        assert metrics["duration_seconds"] == 15.0
        assert "scores" in metrics
        assert "coaching" in metrics

    def test_filler_word_detection(self):
        transcript = "Um, so like I basically um worked on like this project and um it was like really good"
        metrics = self.analyzer.analyze_transcript(transcript, duration_seconds=10.0)

        assert metrics["filler_word_count"] > 3
        assert metrics["filler_ratio"] > 0.1

    def test_empty_transcript(self):
        metrics = self.analyzer.analyze_transcript("", duration_seconds=10.0)
        assert metrics["wpm"] == 0
        assert metrics["word_count"] == 0

    def test_zero_duration(self):
        metrics = self.analyzer.analyze_transcript("Some text here", duration_seconds=0)
        assert metrics["wpm"] == 0

    def test_ideal_speaking_pace(self):
        # ~140 WPM for 60 seconds = 140 words
        words = " ".join(["word"] * 140)
        metrics = self.analyzer.analyze_transcript(words, duration_seconds=60.0)
        assert metrics["scores"]["speaking_pace"] >= 8.0

    def test_fast_speaking_pace(self):
        words = " ".join(["word"] * 200)
        metrics = self.analyzer.analyze_transcript(words, duration_seconds=60.0)
        assert metrics["scores"]["speaking_pace"] < 10.0

    def test_short_response_coaching(self):
        metrics = self.analyzer.analyze_transcript("Yes I agree", duration_seconds=5.0)
        coaching = metrics["coaching"]
        assert any("brief" in tip.lower() for tip in coaching)

    def test_long_response_coaching(self):
        words = " ".join(["word"] * 350)
        metrics = self.analyzer.analyze_transcript(words, duration_seconds=120.0)
        coaching = metrics["coaching"]
        assert any("lengthy" in tip.lower() or "concise" in tip.lower() for tip in coaching)


class TestInterviewServicePhaseTransitions:
    @pytest.mark.asyncio
    async def test_submit_answer_phase_transitions(self):
        import unittest.mock as mock
        from uuid import uuid4
        from app.services.interview_service import InterviewService
        from app.models.interview import Interview, InterviewStatus, InterviewPhase
        from app.models.question import Question, QuestionType

        # Create mocks
        db = mock.MagicMock()
        db.execute = mock.AsyncMock()
        db.flush = mock.AsyncMock()
        cache = mock.AsyncMock()

        # Mock database queries
        mock_interview = Interview(
            id=str(uuid4()),
            user_id=str(uuid4()),
            status=InterviewStatus.IN_PROGRESS,
            current_phase=InterviewPhase.INTRODUCTION,
            total_questions=0,
            target_role="Software Engineer",
            language="english"
        )
        mock_question = Question(
            id=str(uuid4()),
            interview_id=mock_interview.id,
            question_text="Sample question",
            question_type=QuestionType.INTRODUCTION,
            difficulty=5.0,
            order_index=0,
            expected_keywords=""
        )

        mock_result = mock.MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_question
        db.execute.return_value = mock_result

        service = InterviewService(db, cache)

        # Mock internal methods to avoid deep db dependencies
        service._get_interview = mock.AsyncMock(return_value=mock_interview)
        
        # Test transition for idx=4 (next is index 5 which should be TECHNICAL)
        cache.get_interview_state.return_value = {
            "question_index": 4,
            "phase": InterviewPhase.INTRODUCTION.value,
        }
        # Pregenerated question for index 5
        service._get_pregenerated_question = mock.AsyncMock(return_value={
            "id": "q5-id",
            "question_text": "Tech question",
            "question_type": QuestionType.TECHNICAL.value,
            "difficulty": 6.0,
            "order_index": 5,
        })

        result = await service.submit_answer(
            interview_id=uuid4(),
            user_id=uuid4(),
            question_id=uuid4(),
            answer_text="Here is a sufficiently long mock answer that is not considered weak by the service heuristics.",
            duration_seconds=10.0
        )

        assert result["phase"] == InterviewPhase.TECHNICAL.value
        assert result["interview_completed"] is False

        # Test transition for idx=14 (next is index 15 which should be HR)
        cache.get_interview_state.return_value = {
            "question_index": 14,
            "phase": InterviewPhase.TECHNICAL.value,
        }
        service._get_pregenerated_question = mock.AsyncMock(return_value={
            "id": "q15-id",
            "question_text": "HR question",
            "question_type": QuestionType.HR.value,
            "difficulty": 7.0,
            "order_index": 15,
        })

        result = await service.submit_answer(
            interview_id=uuid4(),
            user_id=uuid4(),
            question_id=uuid4(),
            answer_text="Here is another sufficiently long mock answer that passes the word count check of 15 words.",
            duration_seconds=10.0
        )

        assert result["phase"] == InterviewPhase.HR.value
        assert result["interview_completed"] is False

        # Test transition for idx=19 (20 questions completed -> next is coding_assessment)
        cache.get_interview_state.return_value = {
            "question_index": 19,
            "phase": InterviewPhase.HR.value,
        }
        service._get_pregenerated_question = mock.AsyncMock(return_value=None)

        result = await service.submit_answer(
            interview_id=uuid4(),
            user_id=uuid4(),
            question_id=uuid4(),
            answer_text="Last mock answer to complete the whole interview process. 15 words minimum check here too.",
            duration_seconds=10.0
        )

        assert result["phase"] == "coding_assessment"
        assert result["redirect_to_coding"] is True
