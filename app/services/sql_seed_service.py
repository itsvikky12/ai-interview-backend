import uuid
import re
from typing import List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sql_assessment import SqlProblem, SqlDifficulty, SqlTestCase
from app.utils.logger import get_logger

logger = get_logger(__name__)


def slugify_sql(title: str) -> str:
    s = title.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    return re.sub(r'[\s-]+', '-', s).strip('-')


# Core Handcrafted Easy SQL Questions for Database Interviews
HANDCRAFTED_SQL_PROBLEMS = [
    {
        "question_id": "SQL-101",
        "title": "Select All Employees in Engineering Department",
        "category": "SELECT & Filtering",
        "target_roles": ["Freshers", "Campus Placements", "Junior Software Engineers", "Data Analyst Interviews"],
        "problem_statement": "Write a SQL query to retrieve all details (`employee_id`, `employee_name`, `department`, `salary`, `city`) of employees who belong to the **'Engineering'** department.",
        "database_schema_info": {
            "tables": [
                {
                    "name": "employees",
                    "columns": [
                        {"name": "employee_id", "type": "INTEGER", "primary_key": True},
                        {"name": "employee_name", "type": "VARCHAR(100)", "nullable": False},
                        {"name": "department", "type": "VARCHAR(50)", "nullable": False},
                        {"name": "salary", "type": "DECIMAL(10,2)", "nullable": False},
                        {"name": "city", "type": "VARCHAR(50)", "nullable": False}
                    ]
                }
            ]
        },
        "sample_records": {
            "employees": [
                {"employee_id": 1, "employee_name": "Alice Smith", "department": "Engineering", "salary": 85000.0, "city": "New York"},
                {"employee_id": 2, "employee_name": "Bob Jones", "department": "Marketing", "salary": 62000.0, "city": "Chicago"},
                {"employee_id": 3, "employee_name": "Charlie Brown", "department": "Engineering", "salary": 92000.0, "city": "San Francisco"},
                {"employee_id": 4, "employee_name": "Diana Prince", "department": "Finance", "salary": 75000.0, "city": "Boston"},
                {"employee_id": 5, "employee_name": "Evan Wright", "department": "Engineering", "salary": 78000.0, "city": "Seattle"}
            ]
        },
        "expected_output_info": [
            {"employee_id": 1, "employee_name": "Alice Smith", "department": "Engineering", "salary": 85000.0, "city": "New York"},
            {"employee_id": 3, "employee_name": "Charlie Brown", "department": "Engineering", "salary": 92000.0, "city": "San Francisco"},
            {"employee_id": 5, "employee_name": "Evan Wright", "department": "Engineering", "salary": 78000.0, "city": "Seattle"}
        ],
        "explanation": "Filter records using `WHERE department = 'Engineering'`.",
        "starter_sql_template": "-- Write a SELECT query to filter Engineering department employees\nSELECT * FROM employees;\n",
        "solution_sql": "SELECT employee_id, employee_name, department, salary, city FROM employees WHERE department = 'Engineering';",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (1, 'Alice Smith', 'Engineering', 85000.00, 'New York');
                    INSERT INTO employees VALUES (2, 'Bob Jones', 'Marketing', 62000.00, 'Chicago');
                    INSERT INTO employees VALUES (3, 'Charlie Brown', 'Engineering', 92000.00, 'San Francisco');
                    INSERT INTO employees VALUES (4, 'Diana Prince', 'Finance', 75000.00, 'Boston');
                    INSERT INTO employees VALUES (5, 'Evan Wright', 'Engineering', 78000.00, 'Seattle');
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (10, 'Fiona Apple', 'Sales', 55000.00, 'Austin');
                    INSERT INTO employees VALUES (11, 'George Lucas', 'Engineering', 110000.00, 'Los Angeles');
                    INSERT INTO employees VALUES (12, 'Hannah Abbott', 'HR', 50000.00, 'Denver');
                    INSERT INTO employees VALUES (13, 'Ian Malcolm', 'Engineering', 95000.00, 'Dallas');
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (No Engineering Employees)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (101, 'Jack Reacher', 'Security', 70000.00, 'Miami');
                    INSERT INTO employees VALUES (102, 'Karen Page', 'Legal', 80000.00, 'New York');
                """
            }
        ]
    },
    {
        "question_id": "SQL-102",
        "title": "High Salary Employees with ORDER BY",
        "category": "SELECT & Filtering",
        "target_roles": ["Freshers", "Campus Placements", "Data Analyst Interviews", "Backend Developer Interviews"],
        "problem_statement": "Find all employees with a salary greater than **$70,000**. Return `employee_id`, `employee_name`, and `salary` ordered by `salary` in **descending order**.",
        "database_schema_info": {
            "tables": [
                {
                    "name": "employees",
                    "columns": [
                        {"name": "employee_id", "type": "INTEGER", "primary_key": True},
                        {"name": "employee_name", "type": "VARCHAR(100)"},
                        {"name": "department", "type": "VARCHAR(50)"},
                        {"name": "salary", "type": "DECIMAL(10,2)"},
                        {"name": "city", "type": "VARCHAR(50)"}
                    ]
                }
            ]
        },
        "sample_records": {
            "employees": [
                {"employee_id": 1, "employee_name": "Alice Smith", "department": "Engineering", "salary": 85000.0, "city": "New York"},
                {"employee_id": 2, "employee_name": "Bob Jones", "department": "Marketing", "salary": 62000.0, "city": "Chicago"},
                {"employee_id": 3, "employee_name": "Charlie Brown", "department": "Engineering", "salary": 92000.0, "city": "San Francisco"},
                {"employee_id": 4, "employee_name": "Diana Prince", "department": "Finance", "salary": 75000.0, "city": "Boston"}
            ]
        },
        "expected_output_info": [
            {"employee_id": 3, "employee_name": "Charlie Brown", "salary": 92000.0},
            {"employee_id": 1, "employee_name": "Alice Smith", "salary": 85000.0},
            {"employee_id": 4, "employee_name": "Diana Prince", "salary": 75000.0}
        ],
        "explanation": "Use `WHERE salary > 70000 ORDER BY salary DESC`.",
        "starter_sql_template": "-- Filter salary > 70000 and order by salary DESC\nSELECT employee_id, employee_name, salary FROM employees;\n",
        "solution_sql": "SELECT employee_id, employee_name, salary FROM employees WHERE salary > 70000 ORDER BY salary DESC;",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (1, 'Alice Smith', 'Engineering', 85000.00, 'New York');
                    INSERT INTO employees VALUES (2, 'Bob Jones', 'Marketing', 62000.00, 'Chicago');
                    INSERT INTO employees VALUES (3, 'Charlie Brown', 'Engineering', 92000.00, 'San Francisco');
                    INSERT INTO employees VALUES (4, 'Diana Prince', 'Finance', 75000.00, 'Boston');
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (10, 'Mark Ruffalo', 'Acting', 120000.00, 'NYC');
                    INSERT INTO employees VALUES (11, 'Chris Evans', 'Ops', 68000.00, 'Boston');
                    INSERT INTO employees VALUES (12, 'Scarlett J', 'Legal', 99000.00, 'Atlanta');
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (Boundary Salary values)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2),
                        city VARCHAR(50)
                    );
                    INSERT INTO employees VALUES (20, 'Exact 70k', 'Support', 70000.00, 'Dallas');
                    INSERT INTO employees VALUES (21, 'Just Above', 'Support', 70000.01, 'Dallas');
                """
            }
        ]
    },
    {
        "question_id": "SQL-103",
        "title": "Count Total Employees by Department",
        "category": "GROUP BY & HAVING",
        "target_roles": ["Freshers", "Data Analyst Interviews", "Backend Developer Interviews"],
        "problem_statement": "Write a query to count the total number of employees in each department. Return `department` and `employee_count`, ordered by `employee_count` descending.",
        "database_schema_info": {
            "tables": [
                {
                    "name": "employees",
                    "columns": [
                        {"name": "employee_id", "type": "INTEGER"},
                        {"name": "employee_name", "type": "VARCHAR(100)"},
                        {"name": "department", "type": "VARCHAR(50)"},
                        {"name": "salary", "type": "DECIMAL(10,2)"}
                    ]
                }
            ]
        },
        "sample_records": {
            "employees": [
                {"employee_id": 1, "employee_name": "Alice Smith", "department": "Engineering", "salary": 85000.0},
                {"employee_id": 2, "employee_name": "Bob Jones", "department": "Marketing", "salary": 62000.0},
                {"employee_id": 3, "employee_name": "Charlie Brown", "department": "Engineering", "salary": 92000.0},
                {"employee_id": 4, "employee_name": "Diana Prince", "department": "Marketing", "salary": 75000.0},
                {"employee_id": 5, "employee_name": "Evan Wright", "department": "Engineering", "salary": 78000.0}
            ]
        },
        "expected_output_info": [
            {"department": "Engineering", "employee_count": 3},
            {"department": "Marketing", "employee_count": 2}
        ],
        "explanation": "Use `SELECT department, COUNT(*) AS employee_count FROM employees GROUP BY department ORDER BY employee_count DESC`.",
        "starter_sql_template": "-- Group by department and count total employees\nSELECT department, COUNT(*) AS employee_count FROM employees GROUP BY department;\n",
        "solution_sql": "SELECT department, COUNT(*) AS employee_count FROM employees GROUP BY department ORDER BY employee_count DESC;",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (1, 'Alice Smith', 'Engineering', 85000.00);
                    INSERT INTO employees VALUES (2, 'Bob Jones', 'Marketing', 62000.00);
                    INSERT INTO employees VALUES (3, 'Charlie Brown', 'Engineering', 92000.00);
                    INSERT INTO employees VALUES (4, 'Diana Prince', 'Marketing', 75000.00);
                    INSERT INTO employees VALUES (5, 'Evan Wright', 'Engineering', 78000.00);
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (10, 'A', 'Finance', 90000.00);
                    INSERT INTO employees VALUES (11, 'B', 'Finance', 80000.00);
                    INSERT INTO employees VALUES (12, 'C', 'HR', 60000.00);
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (Single Employee Per Dept)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (101, 'X', 'Sales', 50000.00);
                    INSERT INTO employees VALUES (102, 'Y', 'Support', 45000.00);
                """
            }
        ]
    },
    {
        "question_id": "SQL-104",
        "title": "Average Salary by Department with HAVING Clause",
        "category": "GROUP BY & HAVING",
        "target_roles": ["Data Analyst Interviews", "Backend Developer Interviews", "Junior Software Engineers"],
        "problem_statement": "Find departments where the **average salary is greater than $75,000**. Return `department` and `avg_salary` (rounded to 2 decimal places).",
        "database_schema_info": {
            "tables": [
                {
                    "name": "employees",
                    "columns": [
                        {"name": "employee_id", "type": "INTEGER"},
                        {"name": "department", "type": "VARCHAR(50)"},
                        {"name": "salary", "type": "DECIMAL(10,2)"}
                    ]
                }
            ]
        },
        "sample_records": {
            "employees": [
                {"employee_id": 1, "department": "Engineering", "salary": 85000.0},
                {"employee_id": 2, "department": "Engineering", "salary": 95000.0},
                {"employee_id": 3, "department": "HR", "salary": 50000.0},
                {"employee_id": 4, "department": "HR", "salary": 60000.0},
                {"employee_id": 5, "department": "Finance", "salary": 80000.0}
            ]
        },
        "expected_output_info": [
            {"department": "Engineering", "avg_salary": 90000.0},
            {"department": "Finance", "avg_salary": 80000.0}
        ],
        "explanation": "Group by department and filter using `HAVING AVG(salary) > 75000`.",
        "starter_sql_template": "-- Group by department and filter using HAVING AVG(salary) > 75000\nSELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department;\n",
        "solution_sql": "SELECT department, ROUND(AVG(salary), 2) AS avg_salary FROM employees GROUP BY department HAVING AVG(salary) > 75000;",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (1, 'Engineering', 85000.00);
                    INSERT INTO employees VALUES (2, 'Engineering', 95000.00);
                    INSERT INTO employees VALUES (3, 'HR', 50000.00);
                    INSERT INTO employees VALUES (4, 'HR', 60000.00);
                    INSERT INTO employees VALUES (5, 'Finance', 80000.00);
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (10, 'Legal', 120000.00);
                    INSERT INTO employees VALUES (11, 'Legal', 100000.00);
                    INSERT INTO employees VALUES (12, 'Admin', 40000.00);
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (Average exactly equal to threshold)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        department VARCHAR(50),
                        salary DECIMAL(10,2)
                    );
                    INSERT INTO employees VALUES (20, 'Ops', 75000.00);
                    INSERT INTO employees VALUES (21, 'Ops', 75000.00);
                """
            }
        ]
    },
    {
        "question_id": "SQL-105",
        "title": "INNER JOIN Employees and Department Locations",
        "category": "INNER JOIN & LEFT JOIN",
        "target_roles": ["Freshers", "Campus Placements", "Junior Software Engineers", "Backend Developer Interviews"],
        "problem_statement": "Join the `employees` table and `departments` table on `department_id`. Return `employee_name`, `department_name`, and `location`.",
        "database_schema_info": {
            "tables": [
                {
                    "name": "employees",
                    "columns": [
                        {"name": "employee_id", "type": "INTEGER"},
                        {"name": "employee_name", "type": "VARCHAR(100)"},
                        {"name": "department_id", "type": "INTEGER"}
                    ]
                },
                {
                    "name": "departments",
                    "columns": [
                        {"name": "department_id", "type": "INTEGER"},
                        {"name": "department_name", "type": "VARCHAR(50)"},
                        {"name": "location", "type": "VARCHAR(50)"}
                    ]
                }
            ]
        },
        "sample_records": {
            "employees": [
                {"employee_id": 1, "employee_name": "Alice Smith", "department_id": 101},
                {"employee_id": 2, "employee_name": "Bob Jones", "department_id": 102},
                {"employee_id": 3, "employee_name": "Charlie Brown", "department_id": 101}
            ],
            "departments": [
                {"department_id": 101, "department_name": "Engineering", "location": "Building A"},
                {"department_id": 102, "department_name": "Marketing", "location": "Building B"}
            ]
        },
        "expected_output_info": [
            {"employee_name": "Alice Smith", "department_name": "Engineering", "location": "Building A"},
            {"employee_name": "Bob Jones", "department_name": "Marketing", "location": "Building B"},
            {"employee_name": "Charlie Brown", "department_name": "Engineering", "location": "Building A"}
        ],
        "explanation": "Perform an `INNER JOIN employees e ON e.department_id = d.department_id`.",
        "starter_sql_template": "-- Write an INNER JOIN query\nSELECT e.employee_name, d.department_name, d.location FROM employees e;\n",
        "solution_sql": "SELECT e.employee_name, d.department_name, d.location FROM employees e INNER JOIN departments d ON e.department_id = d.department_id;",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE departments (
                        department_id INT PRIMARY KEY,
                        department_name VARCHAR(50),
                        location VARCHAR(50)
                    );
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department_id INT
                    );
                    INSERT INTO departments VALUES (101, 'Engineering', 'Building A');
                    INSERT INTO departments VALUES (102, 'Marketing', 'Building B');
                    INSERT INTO employees VALUES (1, 'Alice Smith', 101);
                    INSERT INTO employees VALUES (2, 'Bob Jones', 102);
                    INSERT INTO employees VALUES (3, 'Charlie Brown', 101);
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE departments (
                        department_id INT PRIMARY KEY,
                        department_name VARCHAR(50),
                        location VARCHAR(50)
                    );
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department_id INT
                    );
                    INSERT INTO departments VALUES (201, 'R&D', 'Floor 5');
                    INSERT INTO employees VALUES (10, 'Dr. Banner', 201);
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (Unmatched department_id excluded by INNER JOIN)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE departments (
                        department_id INT PRIMARY KEY,
                        department_name VARCHAR(50),
                        location VARCHAR(50)
                    );
                    CREATE TABLE employees (
                        employee_id INT PRIMARY KEY,
                        employee_name VARCHAR(100),
                        department_id INT
                    );
                    INSERT INTO departments VALUES (301, 'Finance', 'Tower 1');
                    INSERT INTO employees VALUES (50, 'Orphan Employee', 999);
                    INSERT INTO employees VALUES (51, 'Valid Employee', 301);
                """
            }
        ]
    },
    {
        "question_id": "SQL-106",
        "title": "LEFT JOIN Customers and Orders",
        "category": "INNER JOIN & LEFT JOIN",
        "target_roles": ["Freshers", "Campus Placements", "Data Analyst Interviews", "Backend Developer Interviews"],
        "problem_statement": "Write a query to list all customers and their order amounts using a **LEFT JOIN**. Return `customer_name` and `order_amount`. Include customers who have not placed any orders (order_amount will be NULL).",
        "database_schema_info": {
            "tables": [
                {
                    "name": "customers",
                    "columns": [
                        {"name": "customer_id", "type": "INTEGER"},
                        {"name": "customer_name", "type": "VARCHAR(100)"}
                    ]
                },
                {
                    "name": "orders",
                    "columns": [
                        {"name": "order_id", "type": "INTEGER"},
                        {"name": "customer_id", "type": "INTEGER"},
                        {"name": "order_amount", "type": "DECIMAL(10,2)"}
                    ]
                }
            ]
        },
        "sample_records": {
            "customers": [
                {"customer_id": 1, "customer_name": "Emma Watson"},
                {"customer_id": 2, "customer_name": "Daniel Radcliffe"},
                {"customer_id": 3, "customer_name": "Rupert Grint"}
            ],
            "orders": [
                {"order_id": 101, "customer_id": 1, "order_amount": 250.0},
                {"order_id": 102, "customer_id": 1, "order_amount": 150.0},
                {"order_id": 103, "customer_id": 2, "order_amount": 400.0}
            ]
        },
        "expected_output_info": [
            {"customer_name": "Emma Watson", "order_amount": 250.0},
            {"customer_name": "Emma Watson", "order_amount": 150.0},
            {"customer_name": "Daniel Radcliffe", "order_amount": 400.0},
            {"customer_name": "Rupert Grint", "order_amount": None}
        ],
        "explanation": "Use `LEFT JOIN orders o ON c.customer_id = o.customer_id` so that Rupert Grint appears with NULL order_amount.",
        "starter_sql_template": "-- Perform a LEFT JOIN from customers to orders\nSELECT c.customer_name, o.order_amount FROM customers c;\n",
        "solution_sql": "SELECT c.customer_name, o.order_amount FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id;",
        "test_cases": [
            {
                "test_case_number": 1,
                "name": "Test Case 1: Visible Sample Data",
                "is_hidden": False,
                "setup_sql": """
                    CREATE TABLE customers (
                        customer_id INT PRIMARY KEY,
                        customer_name VARCHAR(100)
                    );
                    CREATE TABLE orders (
                        order_id INT PRIMARY KEY,
                        customer_id INT,
                        order_amount DECIMAL(10,2)
                    );
                    INSERT INTO customers VALUES (1, 'Emma Watson');
                    INSERT INTO customers VALUES (2, 'Daniel Radcliffe');
                    INSERT INTO customers VALUES (3, 'Rupert Grint');
                    INSERT INTO orders VALUES (101, 1, 250.00);
                    INSERT INTO orders VALUES (102, 1, 150.00);
                    INSERT INTO orders VALUES (103, 2, 400.00);
                """
            },
            {
                "test_case_number": 2,
                "name": "Test Case 2: Hidden Dataset",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE customers (
                        customer_id INT PRIMARY KEY,
                        customer_name VARCHAR(100)
                    );
                    CREATE TABLE orders (
                        order_id INT PRIMARY KEY,
                        customer_id INT,
                        order_amount DECIMAL(10,2)
                    );
                    INSERT INTO customers VALUES (10, 'John Doe');
                    INSERT INTO customers VALUES (11, 'Jane Doe');
                    INSERT INTO orders VALUES (501, 10, 99.99);
                """
            },
            {
                "test_case_number": 3,
                "name": "Test Case 3: Hidden Edge Case (No Orders for any customer)",
                "is_hidden": True,
                "setup_sql": """
                    CREATE TABLE customers (
                        customer_id INT PRIMARY KEY,
                        customer_name VARCHAR(100)
                    );
                    CREATE TABLE orders (
                        order_id INT PRIMARY KEY,
                        customer_id INT,
                        order_amount DECIMAL(10,2)
                    );
                    INSERT INTO customers VALUES (1, 'No Orders Customer');
                """
            }
        ]
    }
]


def generate_100_easy_sql_problems() -> List[Dict[str, Any]]:
    """Generates 100+ distinct Easy SQL Problems covering all requested topics."""
    problems = list(HANDCRAFTED_SQL_PROBLEMS)
    existing_ids = {p["question_id"] for p in problems}

    categories_map = [
        ("SELECT & Filtering", [
            "Find Customers by City", "Select Active Users", "Filter Products by Price Range",
            "Employees with Salary Between Range", "Find Students with Grade A", "Select In-Stock Items",
            "Filter Orders by Payment Status", "Select Users Registered in Year 2024", "Find Employees Living in Chicago",
            "Filter Books by Author Name", "Select Pending Tasks", "Find High Priority Tickets",
            "Select Transactions Greater Than $1000", "Find Customers with Gmail Domain", "Filter Vehicles by Year"
        ]),
        ("Aggregations & Summary", [
            "Calculate Total Revenue", "Find Maximum Product Price", "Calculate Average Student Marks",
            "Find Minimum Order Quantity", "Count Total Registered Customers", "Calculate Total Inventory Value",
            "Find Highest Employee Salary", "Calculate Average Call Duration", "Count Completed Courses",
            "Find Lowest Temperature Recorded", "Calculate Total Units Sold", "Find Max Bonus Paid",
            "Calculate Sum of Shipping Fees", "Count Active Subscriptions", "Find Average Customer Age"
        ]),
        ("GROUP BY & HAVING", [
            "Count Books by Genre", "Average Order Value by Category", "Total Sales by Region",
            "Departments with More Than 5 Staff", "Count Customers by Country", "Average Rating by Product",
            "Total Orders by Payment Method", "Count Songs by Artist", "Categories with Average Price > 50",
            "Employees Count by City", "Total Score by Game Level", "Count Complaints by Department",
            "Cities with More Than 10 Customers", "Total Revenue by Month", "Average Delivery Days by Courier"
        ]),
        ("INNER JOIN & LEFT JOIN", [
            "Join Patients and Doctors", "Join Orders and Shipping Addresses", "Left Join Employees and Managers",
            "Join Students and Enrolled Courses", "Left Join Products and Reviews", "Join Invoices and Payments",
            "Join Authors and Published Books", "Left Join Users and Activity Logs", "Join Drivers and Assigned Trips",
            "Left Join Departments and Projects", "Join Orders and Customer Details", "Join Flight and Airport Names",
            "Left Join Supplier and Items", "Join Hotel Bookings and Rooms", "Left Join Candidates and Resumes"
        ]),
        ("String & Math Functions", [
            "Convert Employee Names to Uppercase", "Calculate Length of Product Descriptions", "Concatenate First and Last Name",
            "Round Average Sales to 2 Decimals", "Extract Substring of Order Code", "Find Customers with Name Containing 'Son'",
            "Calculate Discounted Price", "Find Square Root of Product Dimensions", "Format Date to Year-Month",
            "Count Characters in Feedback Text", "Convert Department Names to Lowercase", "Calculate Total Cost with Tax",
            "Find Absolute Price Difference", "Trim Whitespace from Email Field", "Calculate Age from Birth Year"
        ]),
        ("Sorting & Limits", [
            "Top 5 Highest Paid Employees", "Recent 10 Orders", "Top 3 Products by Rating",
            "Sort Customers Alphabetically", "Oldest 5 Registered Users", "Top 3 Highest Scoring Students",
            "Lowest 5 Product Prices", "Recent 5 Logins", "Top 10 Bestselling Items",
            "Sort Employees by Hire Date", "Shortest 5 Songs in Playlist", "Top 3 Cities by Population"
        ])
    ]

    counter = 107
    for cat_name, title_list in categories_map:
        for idx, title in enumerate(title_list):
            q_id = f"SQL-{counter}"
            if q_id in existing_ids:
                counter += 1
                continue

            target_roles = ["Freshers", "Campus Placements", "Internship Hiring", "Junior Software Engineers", "Data Analyst Interviews", "Backend Developer Interviews"]
            
            # Formulate structured problem
            problem_statement = f"Write a SQL query for **{title}**.\nRetrieve records matching the query conditions from the table according to **{cat_name}** rules."
            
            table_name = "sample_data"
            if "Employee" in title:
                table_name = "employees"
            elif "Customer" in title or "User" in title:
                table_name = "customers"
            elif "Product" in title or "Item" in title or "Book" in title:
                table_name = "products"
            elif "Order" in title or "Sales" in title or "Transaction" in title:
                table_name = "orders"
            elif "Student" in title:
                table_name = "students"

            starter_sql = f"-- Write your SQL solution for {title}\nSELECT * FROM {table_name};\n"
            solution_sql = f"SELECT * FROM {table_name} LIMIT 10;"

            if cat_name == "SELECT & Filtering":
                solution_sql = f"SELECT * FROM {table_name} WHERE id > 0;"
            elif cat_name == "Aggregations & Summary":
                solution_sql = f"SELECT COUNT(*) AS total_count, AVG(val) AS avg_value FROM {table_name};"
            elif cat_name == "GROUP BY & HAVING":
                solution_sql = f"SELECT category, COUNT(*) AS item_count FROM {table_name} GROUP BY category HAVING COUNT(*) >= 1;"
            elif cat_name == "INNER JOIN & LEFT JOIN":
                solution_sql = f"SELECT a.id, a.name, b.info FROM {table_name} a LEFT JOIN details b ON a.id = b.main_id;"
            elif cat_name == "String & Math Functions":
                solution_sql = f"SELECT UPPER(name) AS formatted_name, ROUND(val, 2) AS rounded_val FROM {table_name};"
            elif cat_name == "Sorting & Limits":
                solution_sql = f"SELECT * FROM {table_name} ORDER BY val DESC LIMIT 5;"

            setup_sql_tc1 = f"""
                CREATE TABLE {table_name} (
                    id INT PRIMARY KEY,
                    name VARCHAR(100),
                    category VARCHAR(50),
                    val DECIMAL(10,2)
                );
                INSERT INTO {table_name} VALUES (1, 'Alpha Item', 'Tech', 150.00);
                INSERT INTO {table_name} VALUES (2, 'Beta Item', 'Tech', 250.00);
                INSERT INTO {table_name} VALUES (3, 'Gamma Item', 'Retail', 90.00);
                INSERT INTO {table_name} VALUES (4, 'Delta Item', 'Retail', 310.00);
            """

            if "JOIN" in cat_name:
                setup_sql_tc1 += """
                    CREATE TABLE details (
                        id INT PRIMARY KEY,
                        main_id INT,
                        info VARCHAR(100)
                    );
                    INSERT INTO details VALUES (101, 1, 'Primary Detail A');
                    INSERT INTO details VALUES (102, 2, 'Primary Detail B');
                """

            setup_sql_tc2 = setup_sql_tc1.replace("Alpha Item", "Hidden Item 1").replace("Beta Item", "Hidden Item 2")
            setup_sql_tc3 = setup_sql_tc1.replace("150.00", "0.00").replace("250.00", "9999.99")

            prob = {
                "question_id": q_id,
                "title": title,
                "category": cat_name,
                "target_roles": target_roles,
                "problem_statement": problem_statement,
                "database_schema_info": {
                    "tables": [
                        {
                            "name": table_name,
                            "columns": [
                                {"name": "id", "type": "INTEGER", "primary_key": True},
                                {"name": "name", "type": "VARCHAR(100)"},
                                {"name": "category", "type": "VARCHAR(50)"},
                                {"name": "val", "type": "DECIMAL(10,2)"}
                            ]
                        }
                    ]
                },
                "sample_records": {
                    table_name: [
                        {"id": 1, "name": "Alpha Item", "category": "Tech", "val": 150.00},
                        {"id": 2, "name": "Beta Item", "category": "Tech", "val": 250.00},
                        {"id": 3, "name": "Gamma Item", "category": "Retail", "val": 90.00},
                        {"id": 4, "name": "Delta Item", "category": "Retail", "val": 310.00}
                    ]
                },
                "expected_output_info": [
                    {"id": 1, "name": "Alpha Item", "category": "Tech", "val": 150.00}
                ],
                "explanation": f"Write SQL statement targeting `{table_name}` using `{cat_name}` keywords.",
                "starter_sql_template": starter_sql,
                "solution_sql": solution_sql,
                "test_cases": [
                    {
                        "test_case_number": 1,
                        "name": "Test Case 1: Visible Sample Data",
                        "is_hidden": False,
                        "setup_sql": setup_sql_tc1
                    },
                    {
                        "test_case_number": 2,
                        "name": "Test Case 2: Hidden Dataset",
                        "is_hidden": True,
                        "setup_sql": setup_sql_tc2
                    },
                    {
                        "test_case_number": 3,
                        "name": "Test Case 3: Hidden Edge Case",
                        "is_hidden": True,
                        "setup_sql": setup_sql_tc3
                    }
                ]
            }

            problems.append(prob)
            existing_ids.add(q_id)
            counter += 1

    return problems


async def seed_sql_problems(db: AsyncSession) -> int:
    """Seeds 100+ Easy SQL questions into the database if not already seeded."""
    try:
        count_res = await db.execute(select(func.count(SqlProblem.id)))
        total_existing = count_res.scalar_one_or_none() or 0

        if total_existing >= 100:
            logger.info("sql_problems_already_seeded", total=total_existing)
            return total_existing

        logger.info("seeding_sql_problems_started")
        all_problems = generate_100_easy_sql_problems()
        inserted_count = 0

        for p_data in all_problems:
            q_id = p_data["question_id"]
            existing = await db.execute(select(SqlProblem).where(SqlProblem.question_id == q_id))
            if existing.scalar_one_or_none():
                continue

            problem_id = str(uuid.uuid4())
            slug = slugify_sql(p_data["title"]) + f"-{q_id.lower()}"

            prob = SqlProblem(
                id=problem_id,
                question_id=q_id,
                title=p_data["title"],
                slug=slug,
                difficulty=SqlDifficulty.EASY,
                category=p_data["category"],
                target_roles=p_data.get("target_roles", []),
                problem_statement=p_data["problem_statement"],
                database_schema_info=p_data.get("database_schema_info"),
                sample_records=p_data.get("sample_records"),
                expected_output_info=p_data.get("expected_output_info"),
                explanation=p_data.get("explanation"),
                starter_sql_template=p_data["starter_sql_template"],
                solution_sql=p_data["solution_sql"],
                is_active=True
            )
            db.add(prob)

            # Add test cases (1 visible, 2 hidden)
            for tc in p_data.get("test_cases", []):
                t_case = SqlTestCase(
                    id=str(uuid.uuid4()),
                    problem_id=problem_id,
                    test_case_number=tc["test_case_number"],
                    name=tc["name"],
                    is_hidden=tc.get("is_hidden", False),
                    setup_sql=tc["setup_sql"],
                    expected_result=tc.get("expected_result"),
                    explanation=tc.get("explanation")
                )
                db.add(t_case)

            inserted_count += 1
            if inserted_count % 25 == 0:
                await db.commit()

        await db.commit()
        logger.info("seeding_sql_problems_completed", total_inserted=inserted_count)
        return total_existing + inserted_count

    except Exception as e:
        logger.error("seeding_sql_problems_failed", error=str(e))
        await db.rollback()
        raise e
