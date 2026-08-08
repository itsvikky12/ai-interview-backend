import sqlite3
import re
import time
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_mysql_compatibility_functions(conn: sqlite3.Connection):
    """Registers MySQL 8 / Standard SQL functions into SQLite connection."""
    
    # CONCAT function
    def concat(*args):
        return "".join([str(a) for a in args if a is not None])
    
    # NOW function
    def now():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # CURDATE function
    def curdate():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # IFNULL function
    def ifnull(val, default_val):
        return val if val is not None else default_val

    # DATEDIFF function (expr1 - expr2 in days)
    def datediff(expr1, expr2):
        if not expr1 or not expr2:
            return None
        try:
            d1 = datetime.strptime(str(expr1)[:10], "%Y-%m-%d")
            d2 = datetime.strptime(str(expr2)[:10], "%Y-%m-%d")
            return (d1 - d2).days
        except Exception:
            return 0

    # TRUNCATE function
    def truncate_func(val, decimals=0):
        if val is None:
            return None
        try:
            factor = 10 ** int(decimals)
            return math.trunc(float(val) * factor) / factor
        except Exception:
            return val

    # Regexp match function
    def regexp(pattern, string):
        if string is None or pattern is None:
            return False
        try:
            return re.search(pattern, str(string)) is not None
        except Exception:
            return False

    conn.create_function("CONCAT", -1, concat)
    conn.create_function("NOW", 0, now)
    conn.create_function("CURDATE", 0, curdate)
    conn.create_function("IFNULL", 2, ifnull)
    conn.create_function("DATEDIFF", 2, datediff)
    conn.create_function("TRUNCATE", 2, truncate_func)
    conn.create_function("REGEXP", 2, regexp)


class SqlSandboxService:
    @staticmethod
    def validate_query_safety(sql: str) -> Tuple[bool, Optional[str]]:
        """Verifies that the submitted SQL query contains only SELECT/CTE statements."""
        if not sql or not sql.strip():
            return False, "Query cannot be empty."

        clean_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
        clean_sql = clean_sql.strip()

        disallowed_keywords = [
            r'\bDROP\b', r'\bDELETE\b', r'\bUPDATE\b', r'\bINSERT\b',
            r'\bALTER\b', r'\bCREATE\b', r'\bTRUNCATE\b', r'\bGRANT\b',
            r'\bREVOKE\b', r'\bEXEC\b', r'\bEXECUTE\b', r'\bPRAGMA\b',
            r'\bATTACH\b', r'\bDETACH\b', r'\bVACUUM\b'
        ]

        for pattern in disallowed_keywords:
            if re.search(pattern, clean_sql, re.IGNORECASE):
                keyword = pattern.replace(r'\b', '')
                return False, f"Security Violation: '{keyword}' statements are not permitted. Students must write SELECT queries only."

        first_word_match = re.match(r'^\s*([a-zA-Z]+)', clean_sql)
        if not first_word_match:
            return False, "Invalid SQL query format."
        
        first_word = first_word_match.group(1).upper()
        if first_word not in ["SELECT", "WITH"]:
            return False, f"Invalid statement starting with '{first_word}'. Query must start with SELECT or WITH."

        return True, None

    @staticmethod
    def execute_in_sandbox(setup_sql: str, query_sql: str) -> Dict[str, Any]:
        """
        Runs setup_sql and candidate query in a fresh SQLite sandbox instance.
        Returns columns, rows, execution_time_ms, and status.
        """
        is_safe, error_msg = SqlSandboxService.validate_query_safety(query_sql)
        if not is_safe:
            return {
                "status": "ERROR",
                "error_message": error_msg,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0.0,
            }

        conn = sqlite3.connect(":memory:")
        register_mysql_compatibility_functions(conn)
        cursor = conn.cursor()

        try:
            # Set up the database schema and sample data
            if setup_sql and setup_sql.strip():
                cursor.executescript(setup_sql)
                conn.commit()

            start_time = time.perf_counter()
            cursor.execute(query_sql)
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            description = cursor.description
            if not description:
                columns = []
                rows = []
            else:
                columns = [desc[0] for desc in description]
                raw_rows = cursor.fetchall()
                rows = []
                for row in raw_rows:
                    formatted_row = {}
                    for col_idx, col_name in enumerate(columns):
                        val = row[col_idx]
                        if isinstance(val, float):
                            val = round(val, 4)
                        formatted_row[col_name] = val
                    rows.append(formatted_row)

            conn.close()

            return {
                "status": "SUCCESS",
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": execution_time_ms,
                "error_message": None
            }

        except sqlite3.Error as e:
            conn.close()
            return {
                "status": "ERROR",
                "error_message": f"SQL Syntax Error: {str(e)}",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0.0,
            }
        except Exception as e:
            conn.close()
            return {
                "status": "ERROR",
                "error_message": f"Execution Error: {str(e)}",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0.0,
            }

    @staticmethod
    def compare_results(candidate_res: Dict[str, Any], solution_res: Dict[str, Any], require_exact_order: bool = False) -> Tuple[bool, str]:
        """Compares candidate output with solution output."""
        if candidate_res["status"] != "SUCCESS":
            return False, candidate_res.get("error_message") or "Query failed to execute."

        if solution_res["status"] != "SUCCESS":
            return False, "Reference solution execution error."

        c_rows = candidate_res["rows"]
        s_rows = solution_res["rows"]

        if len(c_rows) != len(s_rows):
            return False, f"Row count mismatch: expected {len(s_rows)} rows, but query returned {len(c_rows)} rows."

        if len(c_rows) == 0 and len(s_rows) == 0:
            return True, "Passed (Empty dataset matched)"

        c_cols = set(candidate_res["columns"])
        s_cols = set(solution_res["columns"])

        # Check values equivalence
        def normalize_row(row_dict):
            # Normalize dict values for order-agnostic set/tuple comparison
            return tuple(sorted((str(k).lower(), str(v) if v is not None else "NULL") for k, v in row_dict.items()))

        if require_exact_order:
            for i in range(len(c_rows)):
                if normalize_row(c_rows[i]) != normalize_row(s_rows[i]):
                    return False, f"Mismatch at row {i + 1}: expected {s_rows[i]}, got {c_rows[i]}"
        else:
            c_norm = sorted([normalize_row(r) for r in c_rows])
            s_norm = sorted([normalize_row(r) for r in s_rows])
            if c_norm != s_norm:
                return False, "Data row content mismatch. Expected values do not match returned values."

        return True, "Passed successfully"

    @staticmethod
    def evaluate_sql_submission(
        submitted_sql: str,
        solution_sql: str,
        test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluates submitted SQL query across 3 test cases.
        Calculates score breakdown: Correctness 70%, Optimization 15%, Syntax & Best Practices 10%, Speed 5%.
        Generates AI review analysis.
        """
        tc_results = []
        passed_count = 0
        total_time_ms = 0.0
        require_order = "ORDER BY" in submitted_sql.upper() or "ORDER BY" in solution_sql.upper()

        for tc in test_cases:
            setup_sql = tc.get("setup_sql", "")
            tc_name = tc.get("name", f"Test Case {tc.get('test_case_number')}")
            is_hidden = tc.get("is_hidden", False)

            c_res = SqlSandboxService.execute_in_sandbox(setup_sql, submitted_sql)
            s_res = SqlSandboxService.execute_in_sandbox(setup_sql, solution_sql)

            if c_res["status"] == "SUCCESS":
                total_time_ms += c_res["execution_time_ms"]

            passed, msg = SqlSandboxService.compare_results(c_res, s_res, require_exact_order=require_order)
            if passed:
                passed_count += 1

            tc_results.append({
                "test_case_id": tc.get("id"),
                "test_case_number": tc.get("test_case_number"),
                "name": tc_name,
                "is_hidden": is_hidden,
                "passed": passed,
                "message": msg if not is_hidden or passed else "Hidden test case failed",
                "execution_time_ms": c_res["execution_time_ms"],
                "rows_returned": c_res["row_count"],
                "candidate_preview": c_res["rows"][:5] if not is_hidden else None,
                "expected_preview": s_res["rows"][:5] if not is_hidden else None,
            })

        total_test_cases = max(len(test_cases), 1)
        avg_execution_time = round(total_time_ms / total_test_cases, 2)

        # Weight breakdown:
        # Correct Result → 70%
        correctness_score = round((passed_count / float(total_test_cases)) * 70.0, 2)

        # Query Optimization → 15%
        optimization_score = 15.0
        opt_reasons = []
        upper_sql = submitted_sql.upper()

        if "SELECT *" in upper_sql and ("JOIN" in upper_sql or "GROUP BY" in upper_sql):
            optimization_score -= 5.0
            opt_reasons.append("Avoid 'SELECT *' when querying multiple joined tables; specify explicit column names.")
        if upper_sql.count("JOIN") > 3:
            optimization_score -= 3.0
            opt_reasons.append("High JOIN complexity detected.")
        if "LIKE '%" in upper_sql and "%'" in upper_sql and not upper_sql.startswith("LIKE '%"):
            optimization_score -= 2.0
            opt_reasons.append("Leading wildcards in LIKE ('%term') prevent index usage.")
        optimization_score = max(0.0, round(optimization_score, 2))

        # SQL Syntax & Best Practices → 10%
        syntax_score = 10.0
        keywords = ["SELECT", "FROM", "WHERE", "JOIN", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"]
        used_keywords = [kw for kw in keywords if re.search(r'\b' + kw + r'\b', submitted_sql, re.IGNORECASE)]
        lowercase_kw_count = sum(1 for kw in used_keywords if re.search(r'\b' + kw.lower() + r'\b', submitted_sql))
        
        if lowercase_kw_count > 0 and len(used_keywords) > 0:
            if lowercase_kw_count / len(used_keywords) > 0.5:
                syntax_score -= 3.0
                opt_reasons.append("Format SQL keywords in UPPERCASE (e.g., SELECT, FROM, WHERE) for readability.")
        if not submitted_sql.strip().endswith(";"):
            syntax_score -= 1.0
        syntax_score = max(0.0, round(syntax_score, 2))

        # Execution Speed → 5%
        speed_score = 5.0
        if avg_execution_time > 150:
            speed_score = 2.0
        elif avg_execution_time > 50:
            speed_score = 4.0
        speed_score = round(speed_score, 2)

        final_score = round(correctness_score + optimization_score + syntax_score + speed_score, 1)

        # Quality Rating
        if final_score >= 90:
            quality_rating = "EXCELLENT"
        elif final_score >= 75:
            quality_rating = "GOOD"
        elif final_score >= 50:
            quality_rating = "NEEDS_IMPROVEMENT"
        else:
            quality_rating = "POOR"

        # AI Review Generation
        ai_review = SqlSandboxService._generate_ai_review(
            submitted_sql=submitted_sql,
            solution_sql=solution_sql,
            passed_count=passed_count,
            total_count=total_test_cases,
            final_score=final_score,
            opt_reasons=opt_reasons
        )

        overall_status = "ACCEPTED" if passed_count == total_test_cases else "WRONG_ANSWER"

        return {
            "status": overall_status,
            "passed_test_cases": passed_count,
            "total_test_cases": total_test_cases,
            "execution_time_ms": avg_execution_time,
            "score": final_score,
            "quality_rating": quality_rating,
            "scoring_breakdown": {
                "correctness": correctness_score,
                "correctness_max": 70.0,
                "optimization": optimization_score,
                "optimization_max": 15.0,
                "syntax": syntax_score,
                "syntax_max": 10.0,
                "speed": speed_score,
                "speed_max": 5.0
            },
            "test_case_results": tc_results,
            "ai_review": ai_review
        }

    @staticmethod
    def _generate_ai_review(
        submitted_sql: str,
        solution_sql: str,
        passed_count: int,
        total_count: int,
        final_score: float,
        opt_reasons: List[str]
    ) -> Dict[str, Any]:
        """Generates structured AI review of submitted SQL query."""
        upper_sub = submitted_sql.upper()
        
        has_where = "WHERE" in upper_sub
        has_join = "JOIN" in upper_sub or "LEFT JOIN" in upper_sub or "INNER JOIN" in upper_sub
        has_group_by = "GROUP BY" in upper_sub
        has_aggregates = any(agg in upper_sub for agg in ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX("])

        correctness_summary = (
            f"Query passed {passed_count} of {total_count} test cases with score {final_score}/100."
            if passed_count == total_count else
            f"Query passed {passed_count} of {total_count} test cases. Output needs correction for hidden datasets."
        )

        analysis = {
            "correctness_summary": correctness_summary,
            "where_clause_usage": "Properly filtered dataset using WHERE clause." if has_where else "No WHERE filtering clause used.",
            "join_usage": "Utilized JOIN operations to merge relational table data." if has_join else "Single table query (No JOIN clause).",
            "group_by_usage": "Grouped aggregate records effectively." if has_group_by else "No GROUP BY clause detected.",
            "aggregate_function_usage": "Used aggregate functions (COUNT/SUM/AVG/MIN/MAX) correctly." if has_aggregates else "No SQL aggregate functions used.",
            "optimization_suggestions": opt_reasons if opt_reasons else ["Query execution plan is clean and well optimized."],
            "better_query_alternative": solution_sql,
            "common_mistakes": [
                "Using SELECT * instead of selecting target columns.",
                "Forgetting to alias tables when performing JOINs.",
                "Not handling NULL values in aggregate filters."
            ] if passed_count < total_count else ["No critical syntax or logical mistakes detected."],
            "best_practices": [
                "Use standard UPPERCASE formatting for SQL keywords (SELECT, FROM, WHERE, GROUP BY).",
                "Ensure JOIN conditions reference primary/foreign indexed keys.",
                "Use clear table aliases (e.g. e for employees, d for departments)."
            ]
        }

        return analysis
