"""
Computer Vision analysis service for emotion detection, confidence scoring,
eye contact tracking, and face count detection.

In production, this processes video frames via MediaPipe Face Mesh.
The analysis runs on base64-encoded frames sent from the client.
"""

import math
from dataclasses import dataclass, field
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FrameAnalysis:
    face_count: int = 0
    has_face: bool = False
    eye_contact_score: float = 0.0  # 0-1
    head_pose_yaw: float = 0.0     # degrees, 0 = facing camera
    head_pose_pitch: float = 0.0
    emotion_scores: dict = field(default_factory=dict)
    confidence_score: float = 0.0   # 0-1


class CVAnalysisService:
    """
    Analyzes video frames for:
    - Face detection and count (anti-cheat: multiple faces)
    - Eye contact / gaze tracking
    - Head pose estimation
    - Emotion approximation from facial landmarks
    - Confidence scoring based on composites
    """

    def __init__(self):
        self._mp_face_mesh = None
        self._mp_face_detection = None
        self._initialized = False
        self.frame_history: list[FrameAnalysis] = []

    def _ensure_initialized(self):
        if self._initialized:
            return True
        if getattr(self, "_initialization_failed", False):
            return False
        try:
            import mediapipe as mp
            import numpy as np
            self._mp = mp
            self._np = np
            self._mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=3,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._mp_face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5,
            )
            self._initialized = True
            logger.info("cv_service_initialized")
            return True
        except (ImportError, AttributeError, RuntimeError, OSError) as e:
            self._initialization_failed = True
            logger.warning("mediapipe_not_available", error=str(e), msg="CV analysis will use fallback mode")
            return False

    def analyze_frame_base64(self, frame_b64: str) -> FrameAnalysis:
        """Analyze a base64-encoded video frame."""
        import base64
        try:
            frame_bytes = base64.b64decode(frame_b64)
        except Exception:
            analysis = FrameAnalysis()
            self.frame_history.append(analysis)
            return analysis

        if not self._ensure_initialized():
            analysis = self._fallback_analysis()
            self.frame_history.append(analysis)
            # Keep history bounded
            if len(self.frame_history) > 300:
                self.frame_history = self.frame_history[-300:]
            return analysis

        return self._analyze_frame_bytes(frame_bytes)

    def _analyze_frame_bytes(self, frame_bytes: bytes) -> FrameAnalysis:
        np = self._np
        import cv2

        # Decode image
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return FrameAnalysis()

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape

        analysis = FrameAnalysis()

        # Face detection for count
        det_results = self._mp_face_detection.process(rgb_frame)
        if det_results.detections:
            analysis.face_count = len(det_results.detections)
            analysis.has_face = True
        else:
            analysis.face_count = 0
            analysis.has_face = False

        # Face mesh for detailed analysis
        mesh_results = self._mp_face_mesh.process(rgb_frame)
        if mesh_results.multi_face_landmarks:
            landmarks = mesh_results.multi_face_landmarks[0]  # Primary face
            lm = landmarks.landmark

            # Eye contact from iris landmarks (MediaPipe refine_landmarks=True)
            # Left iris: 468-472, Right iris: 473-477
            # Eye corners: left (33, 133), right (362, 263)
            analysis.eye_contact_score = self._compute_eye_contact(lm, w, h)

            # Head pose from key facial landmarks
            yaw, pitch = self._estimate_head_pose(lm, w, h)
            analysis.head_pose_yaw = yaw
            analysis.head_pose_pitch = pitch

            # Emotion approximation from landmark distances
            analysis.emotion_scores = self._estimate_emotions(lm, w, h)

            # Composite confidence score
            analysis.confidence_score = self._compute_confidence(analysis)

        self.frame_history.append(analysis)

        # Keep only last 300 frames (~10 seconds at 30fps)
        if len(self.frame_history) > 300:
            self.frame_history = self.frame_history[-300:]

        return analysis

    def _compute_eye_contact(self, landmarks, w: int, h: int) -> float:
        """Estimate eye contact by measuring iris position relative to eye boundaries."""
        try:
            # Left eye corners
            left_outer = landmarks[33]
            left_inner = landmarks[133]
            # Left iris center
            left_iris = landmarks[468]

            # Right eye corners
            right_outer = landmarks[362]
            right_inner = landmarks[263]
            # Right iris center
            right_iris = landmarks[473]

            # Compute normalized iris position within eye (0 = outer, 1 = inner)
            def iris_ratio(outer, inner, iris):
                eye_width = math.sqrt((inner.x - outer.x) ** 2 + (inner.y - outer.y) ** 2)
                if eye_width < 0.001:
                    return 0.5
                iris_offset = math.sqrt((iris.x - outer.x) ** 2 + (iris.y - outer.y) ** 2)
                return iris_offset / eye_width

            left_ratio = iris_ratio(left_outer, left_inner, left_iris)
            right_ratio = iris_ratio(right_outer, right_inner, right_iris)

            # When looking at camera, ratio should be ~0.4-0.6
            avg_ratio = (left_ratio + right_ratio) / 2
            deviation = abs(avg_ratio - 0.5)
            eye_contact = max(0.0, 1.0 - deviation * 4)  # Sharp falloff for deviation

            return round(eye_contact, 3)
        except (IndexError, AttributeError):
            return 0.5

    def _estimate_head_pose(self, landmarks, w: int, h: int) -> tuple[float, float]:
        """Estimate head yaw and pitch from nose and face edge landmarks."""
        try:
            nose_tip = landmarks[1]
            left_face = landmarks[234]
            right_face = landmarks[454]
            forehead = landmarks[10]
            chin = landmarks[152]

            # Yaw: nose position relative to face edges
            face_width = right_face.x - left_face.x
            if face_width < 0.001:
                yaw = 0.0
            else:
                nose_offset = (nose_tip.x - left_face.x) / face_width
                yaw = (nose_offset - 0.5) * 60  # Map to roughly -30 to +30 degrees

            # Pitch: nose position relative to forehead-chin line
            face_height = chin.y - forehead.y
            if face_height < 0.001:
                pitch = 0.0
            else:
                nose_vertical = (nose_tip.y - forehead.y) / face_height
                pitch = (nose_vertical - 0.45) * 60

            return round(yaw, 1), round(pitch, 1)
        except (IndexError, AttributeError):
            return 0.0, 0.0

    def _estimate_emotions(self, landmarks, w: int, h: int) -> dict:
        """Rough emotion estimation from facial landmark distances."""
        try:
            # Mouth openness (surprised/speaking)
            upper_lip = landmarks[13]
            lower_lip = landmarks[14]
            mouth_open = abs(lower_lip.y - upper_lip.y)

            # Mouth width (smile)
            mouth_left = landmarks[61]
            mouth_right = landmarks[291]
            mouth_width = abs(mouth_right.x - mouth_left.x)

            # Eyebrow raise (surprised/concerned)
            left_brow = landmarks[70]
            left_eye_top = landmarks[159]
            brow_raise = abs(left_eye_top.y - left_brow.y)

            # Normalize values relative to face size
            nose_bridge = landmarks[6]
            chin = landmarks[152]
            face_height = abs(chin.y - nose_bridge.y) or 0.1

            mouth_open_norm = mouth_open / face_height
            mouth_width_norm = mouth_width / face_height
            brow_raise_norm = brow_raise / face_height

            # Simple emotion scoring
            neutral = 0.3
            happy = min(1.0, mouth_width_norm * 3) * 0.7 if mouth_width_norm > 0.25 else 0.0
            surprised = min(1.0, mouth_open_norm * 8) * 0.5 if mouth_open_norm > 0.05 else 0.0
            concerned = min(1.0, brow_raise_norm * 6) * 0.3 if brow_raise_norm > 0.08 else 0.0

            total = neutral + happy + surprised + concerned or 1.0
            return {
                "neutral": round(neutral / total, 2),
                "happy": round(happy / total, 2),
                "surprised": round(surprised / total, 2),
                "concerned": round(concerned / total, 2),
            }
        except (IndexError, AttributeError):
            return {"neutral": 1.0, "happy": 0.0, "surprised": 0.0, "concerned": 0.0}

    def _compute_confidence(self, analysis: FrameAnalysis) -> float:
        """Composite confidence score from eye contact, head pose, and emotion."""
        eye_score = analysis.eye_contact_score

        # Penalize extreme head angles
        yaw_penalty = max(0, 1.0 - abs(analysis.head_pose_yaw) / 30)
        pitch_penalty = max(0, 1.0 - abs(analysis.head_pose_pitch) / 25)
        pose_score = (yaw_penalty + pitch_penalty) / 2

        # Emotion component: neutral and happy are confident, concerned is not
        emotions = analysis.emotion_scores
        emotion_score = emotions.get("neutral", 0.5) * 0.5 + emotions.get("happy", 0) * 0.8 + (1.0 - emotions.get("concerned", 0)) * 0.3

        confidence = (eye_score * 0.4 + pose_score * 0.3 + min(1.0, emotion_score) * 0.3)
        return round(max(0.0, min(1.0, confidence)), 3)

    def _fallback_analysis(self) -> FrameAnalysis:
        """Used when MediaPipe is not installed."""
        return FrameAnalysis(
            face_count=1,
            has_face=True,
            eye_contact_score=0.7,
            head_pose_yaw=0.0,
            head_pose_pitch=0.0,
            emotion_scores={"neutral": 0.7, "happy": 0.2, "surprised": 0.05, "concerned": 0.05},
            confidence_score=0.7,
        )

    def get_session_summary(self) -> dict:
        """Aggregate analysis across all frames in the session."""
        if not self.frame_history:
            return {
                "avg_eye_contact": 0,
                "avg_confidence": 0,
                "face_present_ratio": 0,
                "multiple_face_count": 0,
                "no_face_count": 0,
                "dominant_emotion": "neutral",
                "gaze_deviation_count": 0,
            }

        total = len(self.frame_history)
        face_present = sum(1 for f in self.frame_history if f.has_face)
        multiple_faces = sum(1 for f in self.frame_history if f.face_count > 1)
        no_face = sum(1 for f in self.frame_history if not f.has_face)
        gaze_deviations = sum(1 for f in self.frame_history if f.eye_contact_score < 0.3)

        avg_eye = sum(f.eye_contact_score for f in self.frame_history) / total
        avg_conf = sum(f.confidence_score for f in self.frame_history) / total

        # Dominant emotion across session
        emotion_totals: dict[str, float] = {}
        for f in self.frame_history:
            for emotion, score in f.emotion_scores.items():
                emotion_totals[emotion] = emotion_totals.get(emotion, 0) + score
        dominant = max(emotion_totals, key=emotion_totals.get) if emotion_totals else "neutral"

        return {
            "avg_eye_contact": round(avg_eye, 3),
            "avg_confidence": round(avg_conf, 3),
            "face_present_ratio": round(face_present / total, 3),
            "multiple_face_count": multiple_faces,
            "no_face_count": no_face,
            "dominant_emotion": dominant,
            "gaze_deviation_count": gaze_deviations,
            "total_frames_analyzed": total,
        }

    def reset(self):
        self.frame_history.clear()
