from app.utils.logger import get_logger

logger = get_logger(__name__)

MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0
ADJUSTMENT_STEP = 0.5
STRONG_ADJUSTMENT_STEP = 1.0


class AdaptiveEngine:
    def __init__(self, initial_difficulty: float = 7.0):
        self.difficulty = max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, initial_difficulty))
        self.score_history: list[float] = []
        self.adjustment_history: list[float] = []

    def update(self, score: float, difficulty_adjustment: int) -> float:
        self.score_history.append(score)

        if len(self.score_history) >= 3:
            recent_avg = sum(self.score_history[-3:]) / 3
            if recent_avg >= 8.0:
                step = STRONG_ADJUSTMENT_STEP
            elif recent_avg >= 6.5:
                step = ADJUSTMENT_STEP
            elif recent_avg <= 3.0:
                step = -STRONG_ADJUSTMENT_STEP
            elif recent_avg <= 4.5:
                step = -ADJUSTMENT_STEP
            else:
                step = 0
        else:
            step = difficulty_adjustment * ADJUSTMENT_STEP

        old = self.difficulty
        self.difficulty = max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, self.difficulty + step))
        self.adjustment_history.append(self.difficulty - old)

        logger.info(
            "difficulty_adjusted",
            old=old,
            new=self.difficulty,
            score=score,
            recent_scores=self.score_history[-3:],
        )
        return self.difficulty

    @property
    def current_difficulty(self) -> float:
        return self.difficulty

    @property
    def average_score(self) -> float:
        if not self.score_history:
            return 0.0
        return sum(self.score_history) / len(self.score_history)

    def get_hint_needed(self) -> bool:
        if len(self.score_history) < 2:
            return False
        return all(s < 4.0 for s in self.score_history[-2:])

    def to_dict(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "score_history": self.score_history,
            "average_score": self.average_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdaptiveEngine":
        engine = cls(initial_difficulty=data.get("difficulty", 5.0))
        engine.score_history = data.get("score_history", [])
        return engine
