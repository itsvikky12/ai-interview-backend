import pytest
from app.services.sql_sandbox_service import SqlSandboxService

def test_validate_query_safety():
    # Valid SELECT queries
    safe, err = SqlSandboxService.validate_query_safety("SELECT * FROM employees WHERE salary > 50000;")
    assert safe is True
    assert err is None

    # Valid CTE query
    safe, err = SqlSandboxService.validate_query_safety("WITH high_sal AS (SELECT * FROM employees) SELECT * FROM high_sal;")
    assert safe is True
    assert err is None

    # Disallowed DDL/DML queries
    safe, err = SqlSandboxService.validate_query_safety("DROP TABLE employees;")
    assert safe is False
    assert "DROP" in err

    safe, err = SqlSandboxService.validate_query_safety("DELETE FROM employees WHERE id = 1;")
    assert safe is False
    assert "DELETE" in err

    safe, err = SqlSandboxService.validate_query_safety("UPDATE employees SET salary = 100000;")
    assert safe is False
    assert "UPDATE" in err


def test_sandbox_execution():
    setup_sql = """
        CREATE TABLE employees (
            id INT PRIMARY KEY,
            name VARCHAR(100),
            salary DECIMAL(10,2)
        );
        INSERT INTO employees VALUES (1, 'Alice', 85000.00);
        INSERT INTO employees VALUES (2, 'Bob', 60000.00);
    """
    query_sql = "SELECT name, salary FROM employees WHERE salary > 70000;"
    
    result = SqlSandboxService.execute_in_sandbox(setup_sql, query_sql)
    assert result["status"] == "SUCCESS"
    assert result["row_count"] == 1
    assert result["rows"][0]["name"] == "Alice"
    assert result["columns"] == ["name", "salary"]


def test_evaluate_sql_submission():
    submitted_sql = "SELECT name, salary FROM employees WHERE salary > 70000;"
    solution_sql = "SELECT name, salary FROM employees WHERE salary > 70000;"

    test_cases = [
        {
            "id": "tc1",
            "test_case_number": 1,
            "name": "Test Case 1: Visible Sample Data",
            "is_hidden": False,
            "setup_sql": """
                CREATE TABLE employees (id INT PRIMARY KEY, name VARCHAR(100), salary DECIMAL(10,2));
                INSERT INTO employees VALUES (1, 'Alice', 85000.00);
                INSERT INTO employees VALUES (2, 'Bob', 60000.00);
            """
        },
        {
            "id": "tc2",
            "test_case_number": 2,
            "name": "Test Case 2: Hidden Dataset",
            "is_hidden": True,
            "setup_sql": """
                CREATE TABLE employees (id INT PRIMARY KEY, name VARCHAR(100), salary DECIMAL(10,2));
                INSERT INTO employees VALUES (10, 'Charlie', 95000.00);
            """
        },
        {
            "id": "tc3",
            "test_case_number": 3,
            "name": "Test Case 3: Hidden Edge Case",
            "is_hidden": True,
            "setup_sql": """
                CREATE TABLE employees (id INT PRIMARY KEY, name VARCHAR(100), salary DECIMAL(10,2));
                INSERT INTO employees VALUES (100, 'Empty', 40000.00);
            """
        }
    ]

    eval_res = SqlSandboxService.evaluate_sql_submission(submitted_sql, solution_sql, test_cases)
    assert eval_res["status"] == "ACCEPTED"
    assert eval_res["passed_test_cases"] == 3
    assert eval_res["total_test_cases"] == 3
    assert eval_res["score"] > 80.0
    assert eval_res["scoring_breakdown"]["correctness"] == 70.0
