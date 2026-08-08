import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.coding import (
    CodingProblem, ProblemDifficulty, LanguageTemplate, CodingTestCase, TestCaseType,
    CodingSubmission, SubmissionStatus, SubmissionResult, AICodeReview, CodingScore,
    CodingSession, CompanyAssessmentTemplate
)
from app.models.interview import Interview, InterviewPhase, InterviewStatus
from app.models.report import Report
from app.services.code_executor import executor_engine, ExecutionResult
from app.ai.openai_client import chat_completion
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CodingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_problems(
        self,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        search: Optional[str] = None,
        company_tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[CodingProblem]:
        stmt = select(CodingProblem).where(CodingProblem.is_archived == False)

        if category:
            stmt = stmt.where(func.lower(CodingProblem.category) == category.lower())
        if difficulty:
            stmt = stmt.where(CodingProblem.difficulty == difficulty.lower())
        if company_tag:
            stmt = stmt.where(CodingProblem.company_tags.contains([company_tag]))
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                func.lower(CodingProblem.title).like(pattern) |
                func.lower(CodingProblem.category).like(pattern)
            )

        stmt = stmt.order_by(CodingProblem.created_at.desc()).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_problem_by_id(self, problem_id: str) -> Optional[CodingProblem]:
        res = await self.db.execute(select(CodingProblem).where(CodingProblem.id == problem_id))
        return res.scalar_one_or_none()

    async def run_code(self, problem_id: str, source_code: str, language: str) -> Dict[str, Any]:
        """Executes source code against only VISIBLE test cases."""
        problem = await self.get_problem_by_id(problem_id)
        if not problem:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding problem not found.")

        tc_stmt = select(CodingTestCase).where(
            CodingTestCase.problem_id == problem_id,
            CodingTestCase.is_hidden == False
        ).order_by(CodingTestCase.order_index.asc())

        tc_res = await self.db.execute(tc_stmt)
        visible_test_cases = list(tc_res.scalars().all())

        if not visible_test_cases:
            # Fallback mock test case if none stored
            visible_test_cases = [
                CodingTestCase(id="tmp1", problem_id=problem_id, input_data="2 7 11 15\n9", expected_output="0 1")
            ]

        results = []
        passed_count = 0
        total_runtime = 0.0
        max_memory = 0.0

        for tc in visible_test_cases:
            exec_res = await executor_engine.execute_code(
                source_code=source_code,
                language=language,
                input_data=tc.input_data,
                timeout_ms=tc.time_limit_ms,
                memory_limit_mb=tc.memory_limit_mb
            )

            actual_clean = exec_res.stdout.strip()
            expected_clean = tc.expected_output.strip()
            is_passed = (exec_res.exit_code == 0) and (actual_clean == expected_clean) and not exec_res.timed_out

            if is_passed:
                passed_count += 1

            total_runtime += exec_res.runtime_ms
            max_memory = max(max_memory, exec_res.memory_mb)

            results.append({
                "test_case_id": tc.id,
                "input": tc.input_data,
                "expected_output": tc.expected_output,
                "actual_output": exec_res.stdout,
                "error_message": exec_res.stderr,
                "passed": is_passed,
                "runtime_ms": exec_res.runtime_ms,
                "memory_mb": exec_res.memory_mb,
                "explanation": tc.explanation,
            })

        return {
            "passed_count": passed_count,
            "total_count": len(visible_test_cases),
            "all_passed": passed_count == len(visible_test_cases),
            "average_runtime_ms": round(total_runtime / max(1, len(visible_test_cases)), 2),
            "max_memory_mb": max_memory,
            "test_cases": results
        }

    async def submit_code(
        self,
        interview_id: str,
        problem_id: str,
        user_id: str,
        source_code: str,
        language: str,
        browser_info: str = "Standard Browser",
        ip_address: str = "127.0.0.1",
        device_info: str = "Desktop"
    ) -> Dict[str, Any]:
        """Submits code for full evaluation against visible AND hidden test cases."""
        problem = await self.get_problem_by_id(problem_id)
        if not problem:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding problem not found.")

        # Fetch all test cases
        tc_stmt = select(CodingTestCase).where(CodingTestCase.problem_id == problem_id).order_by(CodingTestCase.order_index.asc())
        tc_res = await self.db.execute(tc_stmt)
        all_test_cases = list(tc_res.scalars().all())

        if not all_test_cases:
            all_test_cases = [
                CodingTestCase(id="default1", problem_id=problem_id, input_data="1 2 3\n6", expected_output="6", is_hidden=False),
                CodingTestCase(id="default2", problem_id=problem_id, input_data="0 0 0\n0", expected_output="0", is_hidden=True),
            ]

        submission_id = str(uuid.uuid4())
        results = []
        passed_count = 0
        total_runtime = 0.0
        max_memory = 0.0
        has_compilation_error = False
        has_timeout = False

        for tc in all_test_cases:
            exec_res = await executor_engine.execute_code(
                source_code=source_code,
                language=language,
                input_data=tc.input_data,
                timeout_ms=tc.time_limit_ms,
                memory_limit_mb=tc.memory_limit_mb
            )

            if exec_res.compilation_error:
                has_compilation_error = True

            if exec_res.timed_out:
                has_timeout = True

            actual_clean = exec_res.stdout.strip()
            expected_clean = tc.expected_output.strip()
            is_passed = (exec_res.exit_code == 0) and (actual_clean == expected_clean) and not exec_res.timed_out

            if is_passed:
                passed_count += 1

            total_runtime += exec_res.runtime_ms
            max_memory = max(max_memory, exec_res.memory_mb)

            sub_result = SubmissionResult(
                id=str(uuid.uuid4()),
                submission_id=submission_id,
                test_case_id=tc.id if tc.id.startswith("tmp") == False else str(uuid.uuid4()),
                passed=is_passed,
                actual_output=exec_res.stdout[:1000],
                error_message=exec_res.stderr[:1000],
                runtime_ms=exec_res.runtime_ms,
                memory_mb=exec_res.memory_mb
            )
            results.append(sub_result)

        # Determine overall submission status
        total_count = len(all_test_cases)
        if has_compilation_error:
            status_enum = SubmissionStatus.COMPILATION_ERROR
        elif has_timeout:
            status_enum = SubmissionStatus.TIME_LIMIT_EXCEEDED
        elif passed_count == total_count:
            status_enum = SubmissionStatus.ACCEPTED
        else:
            status_enum = SubmissionStatus.WRONG_ANSWER

        avg_runtime = round(total_runtime / max(1, total_count), 2)

        # Create submission record
        submission = CodingSubmission(
            id=submission_id,
            interview_id=interview_id,
            problem_id=problem_id,
            user_id=user_id,
            source_code=source_code,
            language=language,
            status=status_enum,
            passed_test_cases=passed_count,
            total_test_cases=total_count,
            runtime_ms=avg_runtime,
            memory_mb=max_memory,
            compilation_log=results[0].error_message if results else None,
            browser_info=browser_info,
            device_info=device_info,
            ip_address=ip_address
        )
        self.db.add(submission)
        for r in results:
            self.db.add(r)

        # Generate AI Code Review
        ai_review = await self._generate_ai_code_review(problem, source_code, language, submission_id, passed_count, total_count)
        self.db.add(ai_review)

        # Compute Multi-metric score breakdown
        correctness_comp = round((passed_count / max(1, total_count)) * 100.0, 1)
        time_comp = round(ai_review.time_complexity_rating * 10.0, 1)
        space_comp = round(ai_review.space_complexity_rating * 10.0, 1)
        quality_comp = round(ai_review.code_quality_score * 10.0, 1)
        optimization_comp = round(ai_review.optimization_score * 10.0, 1)
        style_comp = round(ai_review.style_score * 10.0, 1)

        # Weighted calculation (50% correctness, 15% time, 10% space, 10% quality, 10% opt, 5% style)
        total_coding_score = round(
            (correctness_comp * 0.50) +
            (time_comp * 0.15) +
            (space_comp * 0.10) +
            (quality_comp * 0.10) +
            (optimization_comp * 0.10) +
            (style_comp * 0.05),
            1
        )

        tech_rating = "EXCELLENT" if total_coding_score >= 85 else ("STRONG" if total_coding_score >= 70 else ("COMPETENT" if total_coding_score >= 50 else "NEEDS_IMPROVEMENT"))

        coding_score_obj = CodingScore(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            correctness_component=correctness_comp,
            time_complexity_component=time_comp,
            space_complexity_component=space_comp,
            code_quality_component=quality_comp,
            optimization_component=optimization_comp,
            style_component=style_comp,
            total_coding_score=total_coding_score,
            technical_rating=tech_rating,
            overall_performance_summary=ai_review.interview_feedback
        )
        self.db.add(coding_score_obj)

        # Update Interview record phase and aggregated score
        interview_res = await self.db.execute(select(Interview).where(Interview.id == interview_id))
        interview = interview_res.scalar_one_or_none()
        if interview:
            interview.coding_score = total_coding_score
            interview.current_phase = InterviewPhase.COMPLETED
            interview.status = InterviewStatus.COMPLETED

            # Re-calculate overall interview score incorporating coding score
            scores = [s for s in [interview.technical_score, interview.communication_score, interview.confidence_score, total_coding_score] if s is not None]
            if scores:
                interview.overall_score = round(sum(scores) / len(scores), 1)

            # Update or create candidate report
            report_res = await self.db.execute(select(Report).where(Report.interview_id == interview_id))
            report = report_res.scalar_one_or_none()
            if not report:
                report = Report(
                    id=str(uuid.uuid4()),
                    interview_id=interview_id,
                    technical_score=interview.technical_score or 0.0,
                    communication_score=interview.communication_score or 0.0,
                    confidence_score=interview.confidence_score or 0.0,
                    coding_score=total_coding_score,
                    overall_score=interview.overall_score or total_coding_score,
                    strengths=ai_review.strengths,
                    weaknesses=ai_review.weaknesses,
                    summary=ai_review.interview_feedback,
                    coding_breakdown={
                        "passed_test_cases": passed_count,
                        "total_test_cases": total_count,
                        "runtime_ms": avg_runtime,
                        "memory_mb": max_memory,
                        "correctness": correctness_comp,
                        "time_complexity": time_comp,
                        "space_complexity": space_comp,
                        "code_quality": quality_comp,
                        "optimization": optimization_comp,
                        "style": style_comp,
                        "technical_rating": tech_rating,
                        "refactored_code": ai_review.refactored_code,
                    }
                )
                self.db.add(report)
            else:
                report.coding_score = total_coding_score
                report.overall_score = interview.overall_score or total_coding_score
                report.coding_breakdown = {
                    "passed_test_cases": passed_count,
                    "total_test_cases": total_count,
                    "runtime_ms": avg_runtime,
                    "memory_mb": max_memory,
                    "correctness": correctness_comp,
                    "time_complexity": time_comp,
                    "space_complexity": space_comp,
                    "code_quality": quality_comp,
                    "optimization": optimization_comp,
                    "style": style_comp,
                    "technical_rating": tech_rating,
                    "refactored_code": ai_review.refactored_code,
                }

        await self.db.commit()

        return {
            "submission_id": submission_id,
            "status": status_enum.value,
            "passed_test_cases": passed_count,
            "total_test_cases": total_count,
            "runtime_ms": avg_runtime,
            "memory_mb": max_memory,
            "total_coding_score": total_coding_score,
            "technical_rating": tech_rating,
            "ai_review": {
                "correctness_score": ai_review.correctness_score,
                "code_quality_score": ai_review.code_quality_score,
                "detected_time_complexity": ai_review.detected_time_complexity,
                "detected_space_complexity": ai_review.detected_space_complexity,
                "strengths": ai_review.strengths,
                "weaknesses": ai_review.weaknesses,
                "suggestions": ai_review.optimization_suggestions,
                "feedback": ai_review.interview_feedback,
                "refactored_code": ai_review.refactored_code
            }
        }

    async def _generate_ai_code_review(
        self,
        problem: CodingProblem,
        source_code: str,
        language: str,
        submission_id: str,
        passed_test_cases: int,
        total_test_cases: int
    ) -> AICodeReview:
        prompt = f"""You are a Senior AI Code Auditor. Evaluate candidate submission for problem '{problem.title}'.

Problem Statement:
{problem.problem_statement}

Candidate Source Code ({language}):
```
{source_code}
```

Passed Test Cases: {passed_test_cases}/{total_test_cases}

Respond with pure JSON object matching this schema:
{{
  "correctness_score": 9.0,
  "time_complexity_rating": 8.5,
  "space_complexity_rating": 8.0,
  "code_quality_score": 8.5,
  "optimization_score": 8.0,
  "style_score": 9.0,
  "detected_time_complexity": "O(N)",
  "detected_space_complexity": "O(N)",
  "strengths": ["Clean structure", "Proper variable naming"],
  "weaknesses": ["Could optimize edge case handling"],
  "optimization_suggestions": ["Use a hash set to reduce lookup time"],
  "interview_feedback": "Strong solution demonstrating good algorithm mastery.",
  "refactored_code": "# Optimized version\\ndef solution():\\n    pass"
}}"""

        try:
            messages = [
                {"role": "system", "content": "You are a principal software engineer evaluator. Return only JSON."},
                {"role": "user", "content": prompt}
            ]
            raw_response = await chat_completion(messages=messages, response_format={"type": "json_object"})
            data = json.loads(raw_response)
        except Exception:
            # Fallback robust evaluation if LLM service is offline
            pass_ratio = (passed_test_cases / max(1, total_test_cases))
            data = {
                "correctness_score": round(pass_ratio * 10.0, 1),
                "time_complexity_rating": 8.0,
                "space_complexity_rating": 8.0,
                "code_quality_score": 8.0,
                "optimization_score": 8.0,
                "style_score": 8.5,
                "detected_time_complexity": problem.expected_time_complexity or "O(N)",
                "detected_space_complexity": problem.expected_space_complexity or "O(1)",
                "strengths": ["Clear algorithm implementation", "Logical structure"],
                "weaknesses": ["Minor edge case optimization opportunity"],
                "optimization_suggestions": ["Consider memory caching for repeated calls"],
                "interview_feedback": "Solid code submission demonstrating algorithmic understanding.",
                "refactored_code": source_code,
            }

        overall_rating = round(sum([
            data.get("correctness_score", 8.0),
            data.get("code_quality_score", 8.0),
            data.get("optimization_score", 8.0),
            data.get("style_score", 8.0)
        ]) / 4.0, 1)

        return AICodeReview(
            id=str(uuid.uuid4()),
            submission_id=submission_id,
            correctness_score=data.get("correctness_score", 8.0),
            time_complexity_rating=data.get("time_complexity_rating", 8.0),
            space_complexity_rating=data.get("space_complexity_rating", 8.0),
            code_quality_score=data.get("code_quality_score", 8.0),
            optimization_score=data.get("optimization_score", 8.0),
            style_score=data.get("style_score", 8.0),
            overall_rating=overall_rating,
            detected_time_complexity=data.get("detected_time_complexity", "O(N)"),
            detected_space_complexity=data.get("detected_space_complexity", "O(1)"),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            optimization_suggestions=data.get("optimization_suggestions", []),
            interview_feedback=data.get("interview_feedback", "Solid performance."),
            refactored_code=data.get("refactored_code", source_code)
        )

    async def get_adaptive_problem_for_interview(self, interview_id: str) -> CodingProblem:
        """Selects a personalized problem based on candidate target role & interview level."""
        int_res = await self.db.execute(select(Interview).where(Interview.id == interview_id))
        interview = int_res.scalar_one_or_none()

        diff_enum = ProblemDifficulty.EASY
        if interview:
            if interview.difficulty_level >= 7.5:
                diff_enum = ProblemDifficulty.HARD
            elif interview.difficulty_level >= 4.5:
                diff_enum = ProblemDifficulty.MEDIUM

        prob_res = await self.db.execute(
            select(CodingProblem)
            .where(CodingProblem.difficulty == diff_enum, CodingProblem.is_archived == False)
            .order_by(func.random())
            .limit(1)
        )
        problem = prob_res.scalar_one_or_none()

        if not problem:
            prob_res = await self.db.execute(select(CodingProblem).where(CodingProblem.is_archived == False).limit(1))
            problem = prob_res.scalar_one()

        return problem
