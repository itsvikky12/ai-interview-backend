from typing import Dict, Any, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.sql_assessment import SqlProblem, SqlDifficulty
from app.models.coding import CodingProblem, ProblemDifficulty
from app.services.sql_seed_service import seed_sql_problems
from app.services.problem_seed_service import seed_coding_problems
from app.utils.logger import get_logger

logger = get_logger(__name__)


class InterviewFlowService:
    """
    Enforces Interview Question Flow Rules:
    
    1. Easy Round:
       - 1 Easy SQL/MySQL Question (10 min)
       - 1 Medium DSA Coding Question (20 min)
    
    2. Medium Round:
       - 1 Easy SQL/MySQL Question (10 min)
       - 1 Medium DSA Coding Question (20 min)
    
    3. Hard Round:
       - 1 Hard DSA Coding Question ONLY (30 min)
       - NO additional Easy or Medium questions asked.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_round_configuration(self, selected_difficulty: str) -> Dict[str, Any]:
        diff = selected_difficulty.lower().strip()
        if diff not in ["easy", "medium", "hard"]:
            diff = "easy"

        # Ensure question banks are seeded
        await seed_sql_problems(self.db)
        await seed_coding_problems(self.db)

        if diff in ["easy", "medium"]:
            # Easy & Medium Rounds: 1 Easy SQL Question (10 min) + 1 Medium DSA Question (20 min)
            
            # Fetch 1 Easy SQL Question
            sql_stmt = (
                select(SqlProblem)
                .where(SqlProblem.difficulty == SqlDifficulty.EASY, SqlProblem.is_active == True)
                .order_by(func.random())
                .limit(1)
            )
            sql_res = await self.db.execute(sql_stmt)
            sql_problem = sql_res.scalar_one_or_none()

            # Fetch 1 Medium DSA Coding Question
            dsa_stmt = (
                select(CodingProblem)
                .where(CodingProblem.difficulty == ProblemDifficulty.MEDIUM, CodingProblem.is_archived == False)
                .order_by(func.random())
                .limit(1)
            )
            dsa_res = await self.db.execute(dsa_stmt)
            dsa_problem = dsa_res.scalar_one_or_none()

            questions = [
                {
                    "question_index": 1,
                    "id": sql_problem.id if sql_problem else "sql_default",
                    "question_id": sql_problem.question_id if sql_problem else "SQL-101",
                    "title": sql_problem.title if sql_problem else "Select All Employees in Engineering Department",
                    "type": "SQL",
                    "topic": "SQL/MySQL",
                    "difficulty": "Easy",
                    "time_limit_minutes": 10,
                    "time_limit_seconds": 600,
                    "problem_data": {
                        "id": sql_problem.id if sql_problem else "",
                        "question_id": sql_problem.question_id if sql_problem else "SQL-101",
                        "title": sql_problem.title if sql_problem else "",
                        "category": sql_problem.category if sql_problem else "Filtering",
                        "problem_statement": sql_problem.problem_statement if sql_problem else "",
                        "starter_sql_template": sql_problem.starter_sql_template if sql_problem else "",
                        "database_schema_info": sql_problem.database_schema_info if sql_problem else {},
                        "sample_records": sql_problem.sample_records if sql_problem else {},
                    }
                },
                {
                    "question_index": 2,
                    "id": dsa_problem.id if dsa_problem else "dsa_default",
                    "question_id": f"DSA-MED-{(dsa_problem.title if dsa_problem else '101')[:10]}",
                    "title": dsa_problem.title if dsa_problem else "Longest Substring Without Repeating Characters",
                    "type": "DSA Coding",
                    "topic": "DSA",
                    "difficulty": "Medium",
                    "time_limit_minutes": 20,
                    "time_limit_seconds": 1200,
                    "problem_data": {
                        "id": dsa_problem.id if dsa_problem else "",
                        "title": dsa_problem.title if dsa_problem else "",
                        "category": dsa_problem.category if dsa_problem else "Sliding Window",
                        "problem_statement": dsa_problem.problem_statement if dsa_problem else "",
                        "constraints": dsa_problem.constraints if dsa_problem else "",
                    }
                }
            ]

            return {
                "selected_difficulty": diff.capitalize(),
                "total_questions": 2,
                "total_time_minutes": 30,
                "summary": "1 Easy SQL/MySQL Question (10 min) + 1 Medium DSA Coding Question (20 min)",
                "questions": questions
            }

        else:
            # Hard Round: 1 Hard DSA Question ONLY (30 min)
            dsa_stmt = (
                select(CodingProblem)
                .where(CodingProblem.difficulty == ProblemDifficulty.HARD, CodingProblem.is_archived == False)
                .order_by(func.random())
                .limit(1)
            )
            dsa_res = await self.db.execute(dsa_stmt)
            dsa_problem = dsa_res.scalar_one_or_none()

            questions = [
                {
                    "question_index": 1,
                    "id": dsa_problem.id if dsa_problem else "dsa_hard_default",
                    "question_id": f"DSA-HARD-{(dsa_problem.title if dsa_problem else 'LRU')[:10]}",
                    "title": dsa_problem.title if dsa_problem else "LRU Cache Design",
                    "type": "DSA Coding",
                    "topic": "DSA",
                    "difficulty": "Hard",
                    "time_limit_minutes": 30,
                    "time_limit_seconds": 1800,
                    "problem_data": {
                        "id": dsa_problem.id if dsa_problem else "",
                        "title": dsa_problem.title if dsa_problem else "",
                        "category": dsa_problem.category if dsa_problem else "System Design Style Programming",
                        "problem_statement": dsa_problem.problem_statement if dsa_problem else "",
                        "constraints": dsa_problem.constraints if dsa_problem else "",
                    }
                }
            ]

            return {
                "selected_difficulty": "Hard",
                "total_questions": 1,
                "total_time_minutes": 30,
                "summary": "1 Hard DSA Coding Question ONLY (30 min)",
                "questions": questions
            }
