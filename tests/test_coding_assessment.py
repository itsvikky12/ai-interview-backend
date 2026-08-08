import pytest
import pytest_asyncio
from app.services.code_executor import executor_engine
from app.services.problem_seed_service import seed_coding_problems
from app.services.coding_service import CodingService
from app.models.coding import CodingProblem, ProblemDifficulty


@pytest.mark.asyncio
async def test_code_executor_python():
    """Verify python code execution sandbox returns accurate stdout and runtime."""
    code = "def solution(a, b):\n    return a + b\n\nimport sys\nlines = sys.stdin.read().split()\nif len(lines) >= 2:\n    print(solution(int(lines[0]), int(lines[1])))"
    res = await executor_engine.execute_code(
        source_code=code,
        language="python",
        input_data="10 25",
        timeout_ms=3000
    )
    assert res.exit_code == 0
    assert res.stdout.strip() == "35"
    assert res.timed_out is False
    assert res.runtime_ms >= 0


@pytest.mark.asyncio
async def test_code_executor_javascript():
    """Verify JavaScript code execution sandbox."""
    code = "const fs = require('fs');\nconst input = fs.readFileSync(0, 'utf-8').trim();\nconsole.log('HELLO ' + input);"
    res = await executor_engine.execute_code(
        source_code=code,
        language="javascript",
        input_data="WORLD",
        timeout_ms=3000
    )
    assert res.exit_code == 0
    assert res.stdout.strip() == "HELLO WORLD"


@pytest.mark.asyncio
async def test_code_executor_timeout():
    """Verify time limit exceeded detection."""
    code = "import time\ntime.sleep(10)"
    res = await executor_engine.execute_code(
        source_code=code,
        language="python",
        input_data="",
        timeout_ms=1000
    )
    assert res.timed_out is True
    assert "Time Limit Exceeded" in res.stderr
