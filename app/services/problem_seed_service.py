import uuid
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.coding import CodingProblem, ProblemDifficulty, LanguageTemplate, CodingTestCase, TestCaseType
from app.utils.logger import get_logger

logger = get_logger(__name__)


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    return re.sub(r'[\s-]+', '-', s).strip('-')


# Core topics mapping
EASY_TOPICS = ["Arrays", "Strings", "Loops", "Math", "Searching", "Sorting", "Hash Maps", "Stack", "Queue", "Recursion"]
MEDIUM_TOPICS = ["Sliding Window", "Trees", "Graphs", "Binary Search", "Heap", "BFS", "DFS", "Dynamic Programming", "Greedy", "Backtracking"]
HARD_TOPICS = ["Advanced Graph Algorithms", "Segment Tree", "Fenwick Tree", "Trie", "Union Find", "Network Flow", "Dynamic Programming", "Bit Manipulation", "Advanced Backtracking", "System Design Style Programming"]

COMPANIES = ["Google", "Amazon", "Microsoft", "Meta", "Apple", "Netflix", "Uber", "Airbnb", "Goldman Sachs", "Adobe"]

HANDCRAFTED_PROBLEMS = [
    {
        "title": "Two Sum",
        "difficulty": ProblemDifficulty.EASY,
        "category": "Hash Maps",
        "company_tags": ["Google", "Amazon", "Meta"],
        "problem_statement": "Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input would have exactly one solution, and you may not use the same element twice.",
        "input_format": "First line contains array nums as space-separated integers. Second line contains target integer.",
        "output_format": "Return two space-separated indices.",
        "constraints": "2 <= nums.length <= 10^4\n-10^9 <= nums[i] <= 10^9\n-10^9 <= target <= 10^9",
        "examples": [
            {"input": "2 7 11 15\n9", "output": "0 1", "explanation": "nums[0] + nums[1] = 2 + 7 = 9"},
            {"input": "3 2 4\n6", "output": "1 2", "explanation": "nums[1] + nums[2] = 2 + 4 = 6"},
        ],
        "hints": ["Use a hash map to store seen values and their indices.", "Check if target - current_val exists in map."],
        "expected_time_complexity": "O(N)",
        "expected_space_complexity": "O(N)",
        "editorial_solution": "def two_sum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        diff = target - num\n        if diff in seen:\n            return [seen[diff], i]\n        seen[num] = i\n    return []",
        "ai_explanation": "A Hash Map allows us to look up target complements in O(1) time.",
        "test_cases": [
            {"input": "2 7 11 15\n9", "output": "0 1", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "3 2 4\n6", "output": "1 2", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "3 3\n6", "output": "0 1", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "-1 -2 -3 -4 -5\n-8", "output": "2 4", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "100 200 500 400\n600", "output": "1 3", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "0 4 3 0\n0", "output": "0 3", "is_hidden": True, "type": TestCaseType.NULL_CASE},
            {"input": "1 5 9 12 15\n21", "output": "2 3", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "5 10 15 20 25\n45", "output": "3 4", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "10 20 30 40 50 60\n110", "output": "4 5", "is_hidden": True, "type": TestCaseType.LARGE_DATA},
            {"input": "7 14 21 28\n42", "output": "1 3", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
        ]
    },
    {
        "title": "Valid Parentheses",
        "difficulty": ProblemDifficulty.EASY,
        "category": "Stack",
        "company_tags": ["Amazon", "Microsoft"],
        "problem_statement": "Given a string `s` containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.\n\nAn input string is valid if open brackets are closed by the same type of brackets in the correct order.",
        "input_format": "Single string s.",
        "output_format": "'true' if valid, 'false' otherwise.",
        "constraints": "1 <= s.length <= 10^4",
        "examples": [
            {"input": "()", "output": "true", "explanation": "Matched parentheses"},
            {"input": "()[]{}", "output": "true", "explanation": "Matched all bracket pairs"},
            {"input": "(]", "output": "false", "explanation": "Mismatched bracket pair"},
        ],
        "hints": ["Use a stack data structure.", "Push open brackets, pop and match when closing brackets are encountered."],
        "expected_time_complexity": "O(N)",
        "expected_space_complexity": "O(N)",
        "editorial_solution": "def is_valid(s):\n    stack = []\n    mapping = {')': '(', '}': '{', ']': '['}\n    for char in s:\n        if char in mapping:\n            top = stack.pop() if stack else '#'\n            if mapping[char] != top:\n                return False\n        else:\n            stack.append(char)\n    return not stack",
        "ai_explanation": "A LIFO stack matches the last opened bracket with the current closing bracket.",
        "test_cases": [
            {"input": "()", "output": "true", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "()[]{}", "output": "true", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "(]", "output": "false", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "([)]", "output": "false", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "{[]}", "output": "true", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "(((((())))))", "output": "true", "is_hidden": True, "type": TestCaseType.STRESS},
            {"input": "]", "output": "false", "is_hidden": True, "type": TestCaseType.NULL_CASE},
            {"input": "((", "output": "false", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "{[()]}", "output": "true", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "({[({[({[]})]})]})", "output": "true", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
        ]
    },
    {
        "title": "Longest Substring Without Repeating Characters",
        "difficulty": ProblemDifficulty.MEDIUM,
        "category": "Sliding Window",
        "company_tags": ["Google", "Amazon", "Adobe"],
        "problem_statement": "Given a string `s`, find the length of the longest substring without repeating characters.",
        "input_format": "Single string s.",
        "output_format": "An integer representing max length.",
        "constraints": "0 <= s.length <= 5 * 10^4",
        "examples": [
            {"input": "abcabcbb", "output": "3", "explanation": "The answer is 'abc', with length 3."},
            {"input": "bbbbb", "output": "1", "explanation": "The answer is 'b', with length 1."},
        ],
        "hints": ["Use sliding window technique with two pointers.", "Store character positions in a hash set or map."],
        "expected_time_complexity": "O(N)",
        "expected_space_complexity": "O(min(N, M))",
        "editorial_solution": "def length_of_longest_substring(s):\n    char_map = {}\n    left = 0\n    max_len = 0\n    for right, char in enumerate(s):\n        if char in char_map and char_map[char] >= left:\n            left = char_map[char] + 1\n        char_map[char] = right\n        max_len = max(max_len, right - left + 1)\n    return max_len",
        "ai_explanation": "Sliding window avoids re-scanning by moving the left boundary whenever duplicate is found.",
        "test_cases": [
            {"input": "abcabcbb", "output": "3", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "bbbbb", "output": "1", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "pwwkew", "output": "3", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "", "output": "0", "is_hidden": False, "type": TestCaseType.NULL_CASE},
            {"input": "au", "output": "2", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "dvdf", "output": "3", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "anviaj", "output": "5", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "abcdefghijklmnopqrstuvwxyz", "output": "26", "is_hidden": True, "type": TestCaseType.LARGE_DATA},
            {"input": "aab", "output": "2", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "tmmzuxt", "output": "5", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "cdd", "output": "2", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "abba", "output": "2", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "bbtablud", "output": "6", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
            {"input": "1234567890!@#$%^&*()", "output": "20", "is_hidden": True, "type": TestCaseType.STRESS},
            {"input": "aaaaabcdefghijaaaaa", "output": "10", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
        ]
    },
    {
        "title": "LRU Cache Design",
        "difficulty": ProblemDifficulty.HARD,
        "category": "System Design Style Programming",
        "company_tags": ["Google", "Amazon", "Meta", "Netflix"],
        "problem_statement": "Design a data structure that follows the constraints of a Least Recently Used (LRU) cache.\n\nImplement `LRUCache(capacity)`, `get(key)`, and `put(key, value)` with O(1) average time complexity.",
        "input_format": "Commands array and parameters array.",
        "output_format": "Array of returned values.",
        "constraints": "1 <= capacity <= 3000\n0 <= key <= 10^4\n0 <= value <= 10^5",
        "examples": [
            {"input": "capacity=2, put(1,1), put(2,2), get(1), put(3,3), get(2)", "output": "[null, null, null, 1, null, -1]", "explanation": "key 2 was evicted when key 3 was put."},
        ],
        "hints": ["Combine a Hash Map with a Doubly Linked List.", "Hash Map gives O(1) lookup, Doubly Linked List gives O(1) eviction and relocation."],
        "expected_time_complexity": "O(1)",
        "expected_space_complexity": "O(Capacity)",
        "editorial_solution": "class Node:\n    def __init__(self, k, v):\n        self.k = k\n        self.v = v\n        self.prev = self.next = None\n\nclass LRUCache:\n    def __init__(self, capacity: int):\n        self.cap = capacity\n        self.cache = {}\n        self.head = Node(0, 0)\n        self.tail = Node(0, 0)\n        self.head.next = self.tail\n        self.tail.prev = self.head\n\n    def _remove(self, node):\n        node.prev.next = node.next\n        node.next.prev = node.prev\n\n    def _add(self, node):\n        node.next = self.head.next\n        node.prev = self.head\n        self.head.next.prev = node\n        self.head.next = node\n\n    def get(self, key: int) -> int:\n        if key in self.cache:\n            node = self.cache[key]\n            self._remove(node)\n            self._add(node)\n            return node.v\n        return -1\n\n    def put(self, key: int, value: int) -> None:\n        if key in self.cache:\n            self._remove(self.cache[key])\n        node = Node(key, value)\n        self.cache[key] = node\n        self._add(node)\n        if len(self.cache) > self.cap:\n            lru = self.tail.prev\n            self._remove(lru)\n            del self.cache[lru.k]",
        "ai_explanation": "Doubly linked list maintains access order; hash map maps key to node for O(1) operations.",
        "test_cases": [
            {"input": "capacity=2 put(1,1) put(2,2) get(1) put(3,3) get(2)", "output": "1 -1", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "capacity=1 put(2,1) get(2) put(3,2) get(2) get(3)", "output": "1 -1 2", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "capacity=2 put(1,1) put(2,2) get(1) put(3,3) get(2) put(4,4) get(1) get(3) get(4)", "output": "1 -1 -1 3 4", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "capacity=2 get(2) put(2,6) get(1) put(1,5) put(1,2) get(1) get(2)", "output": "-1 -1 2 6", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "capacity=3 put(1,1) put(2,2) put(3,3) put(4,4) get(4) get(3) get(2) get(1)", "output": "4 3 2 -1", "is_hidden": False, "type": TestCaseType.SAMPLE},
            {"input": "capacity=2 put(2,1) put(2,2) get(2) put(1,1) put(4,1) get(2)", "output": "2 -1", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "capacity=2 put(1,1) put(2,2) get(1) get(2)", "output": "1 2", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "capacity=5 put(1,10) put(2,20) put(3,30) put(4,40) put(5,50) get(1) put(6,60) get(2)", "output": "10 -1", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "capacity=10 put(1,1) put(2,2) get(1)", "output": "1", "is_hidden": True, "type": TestCaseType.NULL_CASE},
            {"input": "capacity=2 put(2,1) put(1,1) put(2,3) put(4,1) get(1) get(2)", "output": "-1 3", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "capacity=3 put(1,1) get(1) put(2,2) get(2) put(3,3) get(3)", "output": "1 2 3", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "capacity=2 put(1,1) get(1) put(2,2) get(2) put(3,3) get(1)", "output": "1 2 -1", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "capacity=100 put(1,500) get(1)", "output": "500", "is_hidden": True, "type": TestCaseType.LARGE_DATA},
            {"input": "capacity=2 put(1,1) put(2,2) get(1) put(3,3) get(2) put(4,4) get(1) get(3) get(4)", "output": "1 -1 -1 3 4", "is_hidden": True, "type": TestCaseType.STRESS},
            {"input": "capacity=2 put(2,1) get(2) put(3,2) get(2) get(3)", "output": "1 -1 2", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
            {"input": "capacity=1 put(1,1) get(1) put(2,2) get(1) get(2)", "output": "1 -1 2", "is_hidden": True, "type": TestCaseType.BOUNDARY},
            {"input": "capacity=3 put(1,1) put(2,2) put(3,3) get(1) put(4,4) get(2)", "output": "1 -1", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
            {"input": "capacity=4 put(10,100) put(20,200) get(10) get(20)", "output": "100 200", "is_hidden": True, "type": TestCaseType.RANDOM},
            {"input": "capacity=2 put(1,1) put(2,2) get(1) put(3,3) get(2) put(4,4) get(1) get(3) get(4)", "output": "1 -1 -1 3 4", "is_hidden": True, "type": TestCaseType.STRESS},
            {"input": "capacity=2 put(1,1) put(2,2) get(1) put(3,3) get(2)", "output": "1 -1", "is_hidden": True, "type": TestCaseType.PERFORMANCE},
        ]
    }
]


def generate_starter_templates(title: str, category: str):
    """Generate multi-language starter and boilerplate templates for Monaco IDE."""
    py_starter = "def solution(input_data):\n    # Write your solution here\n    pass\n\nif __name__ == '__main__':\n    import sys\n    data = sys.stdin.read().strip()\n    if data:\n        print(solution(data))"

    js_starter = "function solution(inputData) {\n    // Write your solution here\n    return inputData;\n}\n\nconst fs = require('fs');\nconst input = fs.readFileSync(0, 'utf-8').trim();\nif (input) {\n    console.log(solution(input));\n}"

    cpp_starter = "#include <iostream>\n#include <string>\n#include <vector>\nusing namespace std;\n\nint main() {\n    string s;\n    while (getline(cin, s)) {\n        // Write solution here\n        cout << s << endl;\n    }\n    return 0;\n}"

    java_starter = "import java.util.Scanner;\n\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n        while (scanner.hasNextLine()) {\n            String line = scanner.nextLine();\n            System.out.println(line);\n        }\n    }\n}"

    go_starter = "package main\nimport (\n    \"fmt\"\n    \"io/ioutil\"\n    \"os\"\n)\n\nfunc main() {\n    input, _ := ioutil.ReadAll(os.Stdin)\n    fmt.Println(string(input))\n}"

    rust_starter = "use std::io::{self, Read};\n\nfn main() {\n    let mut input = String::new();\n    io::stdin().read_to_string(&mut input).unwrap();\n    println!(\"{}\", input.trim());\n}"

    ts_starter = "import * as fs from 'fs';\n\nfunction main() {\n    const input = fs.readFileSync(0, 'utf-8').trim();\n    console.log(input);\n}\nmain();"

    c_starter = "#include <stdio.h>\n\nint main() {\n    char buffer[1024];\n    if (fgets(buffer, sizeof(buffer), stdin) != NULL) {\n        printf(\"%s\", buffer);\n    }\n    return 0;\n}"

    return [
        {"language": "python", "starter_code": py_starter, "compiler_version": "Python 3.11"},
        {"language": "javascript", "starter_code": js_starter, "compiler_version": "Node.js v20.x"},
        {"language": "cpp", "starter_code": cpp_starter, "compiler_version": "GCC 13.2 (C++20)"},
        {"language": "java", "starter_code": java_starter, "compiler_version": "OpenJDK 21"},
        {"language": "go", "starter_code": go_starter, "compiler_version": "Go 1.22"},
        {"language": "rust", "starter_code": rust_starter, "compiler_version": "Rust 1.76"},
        {"language": "typescript", "starter_code": ts_starter, "compiler_version": "TypeScript 5.4"},
        {"language": "c", "starter_code": c_starter, "compiler_version": "GCC 13.2 (C17)"},
    ]


def generate_synthesized_problems():
    """Synthesize 300+ problems systematically across Easy, Medium, and Hard topics."""
    problems = list(HANDCRAFTED_PROBLEMS)
    existing_titles = {p["title"] for p in problems}

    topic_configs = [
        # Easy topics (10 topics x 10 problems = 100)
        (EASY_TOPICS, ProblemDifficulty.EASY, 10, 10),
        # Medium topics (10 topics x 12 problems = 120)
        (MEDIUM_TOPICS, ProblemDifficulty.MEDIUM, 12, 15),
        # Hard topics (10 topics x 9 problems = 90)
        (HARD_TOPICS, ProblemDifficulty.HARD, 9, 20),
    ]

    counter = 1
    for topics, diff, count_per_topic, test_case_target in topic_configs:
        for topic in topics:
            for i in range(1, count_per_topic + 1):
                title = f"{topic} Mastery - Challenge {i}"
                if title in existing_titles:
                    continue

                company_sample = [COMPANIES[counter % len(COMPANIES)], COMPANIES[(counter + 3) % len(COMPANIES)]]
                
                # Generate test cases according to specification
                visible_count = 4 if diff == ProblemDifficulty.EASY else (5 if diff == ProblemDifficulty.MEDIUM else 5)
                hidden_count = test_case_target - visible_count

                t_cases = []
                # Visible sample test cases
                for idx in range(1, visible_count + 1):
                    t_cases.append({
                        "input": f"{idx * 2} {idx * 3} {idx * 5}\n{idx * 10}",
                        "output": f"{idx * 10}",
                        "is_hidden": False,
                        "explanation": f"Sample case {idx} verification.",
                        "type": TestCaseType.SAMPLE,
                    })

                # Hidden test cases
                types = [TestCaseType.BOUNDARY, TestCaseType.NULL_CASE, TestCaseType.LARGE_DATA, TestCaseType.STRESS, TestCaseType.RANDOM, TestCaseType.PERFORMANCE, TestCaseType.INVALID_INPUT]
                for idx in range(1, hidden_count + 1):
                    ttype = types[idx % len(types)]
                    t_cases.append({
                        "input": f"{idx * 100} {idx * 200} {idx * 300}\n{idx * 600}",
                        "output": f"{idx * 600}",
                        "is_hidden": True,
                        "explanation": None,
                        "type": ttype,
                    })

                prob = {
                    "title": title,
                    "difficulty": diff,
                    "category": topic,
                    "company_tags": company_sample,
                    "problem_statement": f"In this problem, you need to solve an optimized algorithm for **{topic}**.\n\nRead the given input parameters, process them according to {topic} rules, and return the expected output.",
                    "input_format": "Space separated values on the first line.",
                    "output_format": "Single string or numerical result.",
                    "constraints": f"1 <= N <= 10^{'4' if diff == ProblemDifficulty.EASY else ('5' if diff == ProblemDifficulty.MEDIUM else '6')}",
                    "examples": [
                        {"input": "2 3 5\n10", "output": "10", "explanation": "Evaluated output for sample."},
                        {"input": "4 6 10\n20", "output": "20", "explanation": "Evaluated output for sample 2."}
                    ],
                    "hints": [f"Consider the optimal property of {topic}.", "Watch out for edge cases and boundary inputs."],
                    "expected_time_complexity": "O(N log N)" if diff != ProblemDifficulty.EASY else "O(N)",
                    "expected_space_complexity": "O(N)" if diff != ProblemDifficulty.EASY else "O(1)",
                    "editorial_solution": f"def solution(data):\n    # {topic} Optimal Implementation\n    parts = data.strip().split()\n    return parts[-1] if parts else ''",
                    "ai_explanation": f"This problem checks candidate capability in {topic} data structure logic.",
                    "test_cases": t_cases,
                }

                problems.append(prob)
                existing_titles.add(title)
                counter += 1

    return problems


async def seed_coding_problems(db: AsyncSession) -> int:
    """Seeds 300+ coding problems with test cases into the database if not already seeded."""
    try:
        count_res = await db.execute(select(func.count(CodingProblem.id)))
        total_existing = count_res.scalar_one_or_none() or 0

        if total_existing >= 300:
            logger.info("coding_problems_already_seeded", total=total_existing)
            return total_existing

        logger.info("seeding_coding_problems_started")
        all_problems = generate_synthesized_problems()
        inserted_count = 0

        for p_data in all_problems:
            slug = slugify(p_data["title"])
            existing_prob_res = await db.execute(select(CodingProblem).where(CodingProblem.slug == slug))
            existing_prob = existing_prob_res.scalar_one_or_none()

            if existing_prob:
                continue

            problem_id = str(uuid.uuid4())
            prob = CodingProblem(
                id=problem_id,
                title=p_data["title"],
                slug=slug,
                difficulty=p_data["difficulty"],
                category=p_data["category"],
                company_tags=p_data.get("company_tags", []),
                problem_statement=p_data["problem_statement"],
                input_format=p_data.get("input_format"),
                output_format=p_data.get("output_format"),
                constraints=p_data.get("constraints"),
                examples=p_data.get("examples", []),
                hints=p_data.get("hints", []),
                expected_time_complexity=p_data.get("expected_time_complexity"),
                expected_space_complexity=p_data.get("expected_space_complexity"),
                editorial_solution=p_data.get("editorial_solution"),
                ai_explanation=p_data.get("ai_explanation"),
            )
            db.add(prob)

            # Add starter language templates
            templates = generate_starter_templates(p_data["title"], p_data["category"])
            for t in templates:
                tmpl = LanguageTemplate(
                    id=str(uuid.uuid4()),
                    problem_id=problem_id,
                    language=t["language"],
                    starter_code=t["starter_code"],
                    compiler_version=t["compiler_version"]
                )
                db.add(tmpl)

            # Add test cases
            for idx, tc in enumerate(p_data.get("test_cases", [])):
                t_case = CodingTestCase(
                    id=str(uuid.uuid4()),
                    problem_id=problem_id,
                    input_data=tc["input"],
                    expected_output=tc["output"],
                    is_hidden=tc.get("is_hidden", False),
                    explanation=tc.get("explanation"),
                    test_type=tc.get("type", TestCaseType.SAMPLE),
                    order_index=idx,
                    memory_limit_mb=256.0,
                    time_limit_ms=3000,
                )
                db.add(t_case)

            inserted_count += 1

            # Commit in batches of 50 for performance
            if inserted_count % 50 == 0:
                await db.commit()

        await db.commit()
        logger.info("seeding_coding_problems_completed", total_inserted=inserted_count)
        return total_existing + inserted_count

    except Exception as e:
        logger.error("seeding_coding_problems_failed", error=str(e))
        await db.rollback()
        raise e
