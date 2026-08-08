import re
from app.utils.logger import get_logger

logger = get_logger(__name__)

FILLER_WORDS = {
    "um", "uh", "like", "you know", "basically", "actually", "literally",
    "so", "well", "right", "okay", "i mean", "kind of", "sort of",
    "hmm", "er", "ah", "umm",
}


TECH_KEYWORDS = {
    "python", "javascript", "typescript", "react", "next.js", "nextjs", "vue", "angular",
    "node", "nodejs", "fastapi", "django", "flask", "express", "sql", "postgresql", "mongodb",
    "redis", "docker", "kubernetes", "aws", "gcp", "azure", "git", "github", "machine learning",
    "deep learning", "ai", "llm", "nlp", "pytorch", "tensorflow", "scikit-learn", "ci/cd",
    "api", "graphql", "rest", "microservices", "agile", "scrum"
}

SENTIMENT_POSITIVE = {"confident", "good", "great", "successfully", "solved", "created", "built", "implemented", "optimized", "achieved", "learned", "passion", "excited", "happy", "love"}
SENTIMENT_NEGATIVE = {"difficult", "hard", "struggled", "failed", "unhappy", "sad", "worry", "afraid", "slow", "error", "bug"}


class SpeechAnalyzer:
    def analyze_transcript(self, transcript: str, duration_seconds: float) -> dict:
        if not transcript or duration_seconds <= 0:
            return self._empty_metrics()

        words = transcript.lower().split()
        word_count = len(words)
        wpm = (word_count / duration_seconds) * 60 if duration_seconds > 0 else 0

        filler_count = 0
        transcript_lower = transcript.lower()
        for filler in FILLER_WORDS:
            filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', transcript_lower))

        # Estimate pauses from sentence boundaries and ellipses
        pause_indicators = transcript.count("...") + transcript.count("—") + transcript.count(". . .")
        sentences = [s.strip() for s in re.split(r'[.!?]+', transcript) if s.strip()]
        avg_sentence_length = word_count / max(len(sentences), 1)

        # Scoring
        wpm_score = self._score_wpm(wpm)
        filler_ratio = filler_count / max(word_count, 1)
        filler_score = max(0, 10 - (filler_ratio * 100))
        clarity_score = min(10, avg_sentence_length / 3) if avg_sentence_length < 30 else max(5, 10 - (avg_sentence_length - 30) / 5)

        coaching = self._generate_coaching(wpm, filler_count, filler_ratio, pause_indicators, word_count)

        # Sentiment and technical keyword detection
        detected_keywords = []
        for kw in TECH_KEYWORDS:
            if re.search(r'\b' + re.escape(kw) + r'\b', transcript_lower):
                detected_keywords.append(kw.capitalize())

        pos_count = sum(1 for w in SENTIMENT_POSITIVE if re.search(r'\b' + re.escape(w) + r'\b', transcript_lower))
        neg_count = sum(1 for w in SENTIMENT_NEGATIVE if re.search(r'\b' + re.escape(w) + r'\b', transcript_lower))
        
        if pos_count > neg_count:
            sentiment = "Confident & Positive"
        elif neg_count > pos_count:
            sentiment = "Reflective / Problem-Solving"
        else:
            sentiment = "Neutral & Professional"

        skills_extracted = detected_keywords[:3]
        project_mentions = []
        if "project" in transcript_lower or "internship" in transcript_lower:
            project_mentions.append("Demonstrated Project Experience")

        metrics = {
            "wpm": round(wpm, 1),
            "word_count": word_count,
            "filler_word_count": filler_count,
            "filler_ratio": round(filler_ratio, 3),
            "pause_count": pause_indicators,
            "avg_sentence_length": round(avg_sentence_length, 1),
            "duration_seconds": round(duration_seconds, 1),
            "scores": {
                "speaking_pace": round(wpm_score, 1),
                "filler_words": round(filler_score, 1),
                "clarity": round(clarity_score, 1),
                "overall": round((wpm_score + filler_score + clarity_score) / 3, 1),
            },
            "coaching": coaching,
            "sentiment": sentiment,
            "detected_keywords": detected_keywords,
            "skills_extracted": skills_extracted,
            "project_mentions": project_mentions,
        }

        logger.info("speech_analyzed", wpm=metrics["wpm"], fillers=filler_count)
        return metrics

    def _score_wpm(self, wpm: float) -> float:
        # Ideal range: 120-160 WPM
        if 120 <= wpm <= 160:
            return 10.0
        elif 100 <= wpm < 120 or 160 < wpm <= 180:
            return 8.0
        elif 80 <= wpm < 100 or 180 < wpm <= 200:
            return 6.0
        elif wpm < 80:
            return 4.0
        else:
            return 5.0

    def _generate_coaching(self, wpm: float, filler_count: int, filler_ratio: float, pauses: int, word_count: int) -> list[str]:
        tips = []
        if wpm < 100:
            tips.append("Your speaking pace is slow. Try to speak a bit faster to maintain engagement. Aim for 120-160 words per minute.")
        elif wpm > 180:
            tips.append("You're speaking quite fast. Slow down slightly to ensure clarity. Aim for 120-160 words per minute.")

        if filler_ratio > 0.05:
            tips.append(f"You used {filler_count} filler words. Practice pausing silently instead of using fillers like 'um' or 'like'.")
        elif filler_count > 0:
            tips.append(f"Good control of filler words ({filler_count} total). Keep practicing for even smoother delivery.")

        if pauses > 5:
            tips.append("You had several long pauses. While thinking time is fine, try to structure your thoughts before speaking.")

        if word_count < 30:
            tips.append("Your response was quite brief. Try to elaborate more and provide specific examples.")
        elif word_count > 300:
            tips.append("Your response was lengthy. Practice being more concise while keeping the key points.")

        if not tips:
            tips.append("Your speaking delivery was solid. Keep practicing to maintain this level.")

        return tips

    def _empty_metrics(self) -> dict:
        return {
            "wpm": 0, "word_count": 0, "filler_word_count": 0, "filler_ratio": 0,
            "pause_count": 0, "avg_sentence_length": 0, "duration_seconds": 0,
            "scores": {"speaking_pace": 0, "filler_words": 0, "clarity": 0, "overall": 0},
            "coaching": [],
        }
