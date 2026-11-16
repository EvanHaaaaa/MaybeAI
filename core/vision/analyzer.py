from typing import Dict, Any, Tuple, Optional
from PIL import Image

from core.vision.models import VisualSceneType, VisualObservation


class VisualAnalyzer:
    """
    Analyzes captured screen images using computer vision color heuristics,
    scene decomposition, and event detection.
    """

    @classmethod
    def analyze_frame(
        cls,
        image: Image.Image,
        previous_observation: Optional[VisualObservation] = None,
        change_delta: float = 0.0,
        hint_scene: Optional[str] = None
    ) -> VisualObservation:
        """
        Processes an image and returns a detailed VisualObservation object.
        """
        # If an explicit hint or simulation preset was passed, leverage it directly
        if hint_scene and hint_scene in [s.value for s in VisualSceneType]:
            detected_type = hint_scene
            confidence = 0.96
        else:
            detected_type, confidence = cls._classify_scene(image)

        labels = {
            VisualSceneType.MINECRAFT_DEFEAT.value: "Minecraft (Kekalahan / You Died!)",
            VisualSceneType.MINECRAFT_DIAMOND.value: "Minecraft (Menemukan Diamond Vein)",
            VisualSceneType.MINECRAFT_PLAYING.value: "Minecraft (Eksplorasi Dunia)",
            VisualSceneType.CHESS_MATCH.value: "Catur (Pertandingan Papan Taktis)",
            VisualSceneType.CHESS_GAMEOVER.value: "Catur (Skakmat / Game Over)",
            VisualSceneType.VIDEO_WATCHING.value: "Video Streaming / YouTube Player",
            VisualSceneType.DESKTOP_GENERAL.value: "Desktop Workspace / Code Editor",
            VisualSceneType.UNKNOWN.value: "Visual Umum Tidak Teridentifikasi"
        }

        summaries = {
            VisualSceneType.MINECRAFT_DEFEAT.value: "Player mengalami kekalahan tragis di Minecraft! Layar bernuansa merah dengan teks 'YOU DIED'.",
            VisualSceneType.MINECRAFT_DIAMOND.value: "Ditemukan bijih berlian bercahaya biru cyan di dalam gua gelap Y=-58!",
            VisualSceneType.MINECRAFT_PLAYING.value: "Sedang bermain Minecraft: pemandangan horizon langit, padang rumput, dan hotbar aktif.",
            VisualSceneType.CHESS_MATCH.value: "Papan catur aktif dengan posisi bidak taktis dalam pertempuran ELO.",
            VisualSceneType.CHESS_GAMEOVER.value: "Pertandingan catur berakhir dengan skakmat mutlak di papan!",
            VisualSceneType.VIDEO_WATCHING.value: "Sedang menonton video dengan player bar YouTube di layar.",
            VisualSceneType.DESKTOP_GENERAL.value: "Layar menampilkan lingkungan kerja desktop dan jendela code editor IDE.",
            VisualSceneType.UNKNOWN.value: "Layar monitor aktif dengan aktivitas umum."
        }

        # Event classification
        is_event = False
        event_type = None

        if detected_type == VisualSceneType.MINECRAFT_DEFEAT.value:
            is_event = True
            event_type = "player_defeat"
        elif detected_type == VisualSceneType.MINECRAFT_DIAMOND.value:
            is_event = True
            event_type = "diamond_found"
        elif detected_type == VisualSceneType.CHESS_GAMEOVER.value:
            is_event = True
            event_type = "checkmate"
        elif detected_type == VisualSceneType.VIDEO_WATCHING.value:
            is_event = True
            event_type = "video_reaction"
        elif change_delta >= 0.20:
            is_event = True
            event_type = "scene_change"

        details = {
            "image_size": f"{image.width}x{image.height}",
            "dominant_scene": detected_type,
            "scene_confidence_pct": int(confidence * 100),
            "screen_changed_pct": int(change_delta * 100)
        }

        return VisualObservation(
            scene_type=detected_type,
            scene_label=labels.get(detected_type, "Unknown Scene"),
            confidence=confidence,
            summary=summaries.get(detected_type, "Layar termonitor."),
            details=details,
            change_delta=change_delta,
            is_event=is_event,
            event_type=event_type
        )

    @classmethod
    def _classify_scene(cls, img: Image.Image) -> Tuple[str, float]:
        """
        Fast multi-stage heuristics:
        1. Red vignette death screen detection
        2. Cyan diamond ore glow detection
        3. Checkered chess pattern detection
        4. YouTube red scrubber detection
        5. Sky/grass horizon detection
        """
        # Downscale to a normalized 128x72 for fast pixel statistics
        thumb = img.resize((128, 72)).convert("RGB")
        w, h = thumb.size
        pixels = thumb.load()

        total = w * h
        red_tint_count = 0
        cyan_glow_count = 0
        sky_blue_count = 0
        grass_green_count = 0
        yt_red_bar_count = 0

        # Scan pixels
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]

                # Red Death Screen: high R, very low G and B
                if r > 110 and g < 45 and b < 45:
                    red_tint_count += 1

                # Cyan Diamond Glow: high B and G, low R
                if b > 180 and g > 180 and r < 80:
                    cyan_glow_count += 1

                # Sky Blue (top half)
                if y < h // 2 and b > 190 and g > 130 and r < 140:
                    sky_blue_count += 1

                # Grass Green (bottom half)
                if y >= h // 2 and g > 110 and r < 90 and b < 70:
                    grass_green_count += 1

                # YouTube Red Scrubber line near bottom
                if y > int(h * 0.75) and r > 180 and g < 50 and b < 60:
                    yt_red_bar_count += 1

        # Evaluate heuristics
        # 1. Defeat Red Screen (more than 18% of screen dominated by deep death red)
        if (red_tint_count / total) > 0.18:
            return VisualSceneType.MINECRAFT_DEFEAT.value, 0.94

        # 2. Diamond Vein (dense cluster of cyan pixels in dark surrounding)
        if cyan_glow_count >= 15:
            return VisualSceneType.MINECRAFT_DIAMOND.value, 0.92

        # 3. Video Player with Red Scrubber
        if yt_red_bar_count >= 12:
            return VisualSceneType.VIDEO_WATCHING.value, 0.88

        # 4. Minecraft Horizon (sky in upper half + grass in bottom half)
        if (sky_blue_count / (total // 2)) > 0.20 and (grass_green_count / (total // 2)) > 0.15:
            return VisualSceneType.MINECRAFT_PLAYING.value, 0.90

        # 5. Chess Board Checkered Pattern Check
        # Sample middle rows for alternating dark/light blocks
        mid_y = h // 2
        transitions = 0
        last_is_light = None
        for x in range(int(w * 0.25), int(w * 0.75), 4):
            r, g, b = pixels[x, mid_y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            is_light = lum > 140
            if last_is_light is not None and is_light != last_is_light:
                transitions += 1
            last_is_light = is_light

        if transitions >= 6:
            return VisualSceneType.CHESS_MATCH.value, 0.85

        return VisualSceneType.DESKTOP_GENERAL.value, 0.80
