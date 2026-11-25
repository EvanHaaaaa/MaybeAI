import time
import threading
from typing import Optional, Dict, Any, List, Callable
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

from core.vision.models import VisualSceneType, VisualObservation, VisionConfig
from core.vision.capture import ScreenCaptureManager
from core.vision.analyzer import VisualAnalyzer
from core.vision.vlm import MultimodalVisionModel


class VisionEngine:
    """
    Core Visual Perception & Screen Awareness Engine for Eve Maybe.
    Enables Eve to perceive what is happening on screen in real time:
    - Recognizes games and environments (Minecraft, Chess, Videos, Desktop).
    - Detects player defeat/death ("You Died!"), victories, and diamond veins.
    - Observes visual changes and triggers spontaneous, grounded streamer commentary.
    """

    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self.capture_mgr = ScreenCaptureManager()
        
        self.current_observation: Optional[VisualObservation] = None
        self.recent_observations: List[VisualObservation] = []
        self._previous_image: Optional[Any] = None
        
        self.last_capture_time: float = 0.0
        self.last_commentary_time: float = 0.0
        self.is_auto_active: bool = self.config.auto_perception
        self._lock = threading.Lock()

        # Optional event broadcast callback
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # Initialize with an initial baseline desktop observation
        self._initialize_baseline()

    def _initialize_baseline(self):
        """Creates an initial baseline desktop perception."""
        if not getattr(self.capture_mgr, "has_pil", True) or not HAS_PIL:
            obs = VisualObservation(
                scene_type=VisualSceneType.DESKTOP_GENERAL.value,
                summary="Modul visual offline (Pillow/mss belum terpasang).",
                eve_commentary="[emotion: thinking] Mataku agak buram nih, library Pillow belum terpasang. Tapi kita tetap bisa ngobrol dan mabar kok!",
                change_delta=0.0
            )
            self.current_observation = obs
            self.recent_observations.append(obs)
            self.last_capture_time = time.time()
            self.last_commentary_time = time.time()
            return

        mock_img = self.capture_mgr.generate_mock_scene(VisualSceneType.DESKTOP_GENERAL.value)
        self._previous_image = mock_img
        b64 = ScreenCaptureManager.to_base64_data_url(
            mock_img,
            max_size=(self.config.max_thumbnail_width, self.config.max_thumbnail_height)
        )
        obs = VisualAnalyzer.analyze_frame(mock_img, change_delta=0.0)
        obs.thumbnail_base64 = b64
        obs.eve_commentary = "[emotion: happy] Sistem mata visual Eve sudah aktif! Sekarang aku bisa melihat apa pun yang kamu buka di layar. [action: wink]"
        self.current_observation = obs
        self.recent_observations.append(obs)
        self.last_capture_time = time.time()
        self.last_commentary_time = time.time()

    def set_broadcast_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self.broadcast_callback = callback

    def perceive(
        self,
        simulated_scene: Optional[str] = None,
        force_commentary: bool = False,
        mood_directive: str = "",
        dominant_mood: str = "CHILL_NEUTRAL"
    ) -> VisualObservation:
        """
        Executes a visual perception cycle:
        1. Captures live screen or renders simulated scene.
        2. Computes pixel difference from previous frame.
        3. Analyzes scene and detects visual events (defeat, diamond, checkmate, video).
        4. Generates Eve's visual commentary if an event or major change occurred.
        5. Notifies listener / orchestrator callback if registered.
        """
        now = time.time()

        # 1. Capture or synthesize image
        if simulated_scene:
            img = self.capture_mgr.generate_mock_scene(simulated_scene)
            hint_scene = simulated_scene
        else:
            try:
                img = self.capture_mgr.capture_screen()
                hint_scene = None
            except Exception:
                img = self.capture_mgr.generate_mock_scene(VisualSceneType.DESKTOP_GENERAL.value)
                hint_scene = VisualSceneType.DESKTOP_GENERAL.value

        with self._lock:
            self.last_capture_time = now

            # 2. Compute visual change diff
            diff_delta = 0.0
            if self._previous_image is not None:
                diff_delta = ScreenCaptureManager.compute_image_diff(self._previous_image, img)
            self._previous_image = img

            # 3. Analyze scene & classify events
            obs = VisualAnalyzer.analyze_frame(
                image=img,
                previous_observation=self.current_observation,
                change_delta=diff_delta,
                hint_scene=hint_scene
            )

            # 4. Generate thumbnail base64
            obs.thumbnail_base64 = ScreenCaptureManager.to_base64_data_url(
                img,
                max_size=(self.config.max_thumbnail_width, self.config.max_thumbnail_height)
            )

            # 5. Check if Eve should speak / comment
            time_since_last_comment = now - self.last_commentary_time
            should_speak = force_commentary or (
                (obs.is_event or diff_delta >= self.config.change_threshold)
                and time_since_last_comment >= self.config.cooldown_commentary_sec
            )

            if should_speak:
                commentary = MultimodalVisionModel.generate_commentary(
                    observation=obs,
                    mood_directive=mood_directive,
                    dominant_mood=dominant_mood
                )
                obs.eve_commentary = commentary
                self.last_commentary_time = now

            self.current_observation = obs
            self.recent_observations.append(obs)
            if len(self.recent_observations) > 15:
                self.recent_observations.pop(0)

            # 6. Trigger broadcast callback if present
            if self.broadcast_callback and callable(self.broadcast_callback):
                try:
                    self.broadcast_callback(self.get_state())
                except Exception as e:
                    print(f"[VisionEngine] Broadcast callback error: {e}")

        return obs

    def set_auto_perception(self, enabled: bool):
        self.is_auto_active = enabled
        self.config.auto_perception = enabled

    def get_state(self) -> Dict[str, Any]:
        """Returns serializable state for Web UI and REST/WS APIs."""
        return {
            "is_auto_active": self.is_auto_active,
            "capture_interval_sec": self.config.capture_interval_sec,
            "last_capture_time": self.last_capture_time,
            "last_commentary_time": self.last_commentary_time,
            "current_observation": self.current_observation.to_dict() if self.current_observation else None,
            "recent_count": len(self.recent_observations),
            "recent_observations": [o.to_dict() for o in reversed(self.recent_observations[-6:])]
        }
