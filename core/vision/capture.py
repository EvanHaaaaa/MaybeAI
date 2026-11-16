import io
import base64
import time
from typing import Tuple, Optional, Any
from PIL import Image, ImageDraw, ImageFont
import mss

from core.vision.models import VisualSceneType


class ScreenCaptureManager:
    """
    Handles real-time display capturing via mss and synthetic scene generation
    for headless environments, stream simulations, and automated unit testing.
    """

    def __init__(self):
        self._sct: Optional[mss.mss] = None

    def _get_sct(self) -> Any:
        if self._sct is None:
            # mss.MSS is the newer entrypoint, fall back to mss.mss for older versions
            cls_mss = getattr(mss, "MSS", mss.mss)
            self._sct = cls_mss()
        return self._sct

    def capture_screen(self, monitor_idx: int = 1) -> Image.Image:
        """
        Captures the live primary monitor screen using mss.
        Falls back to desktop synthetic frame if screen capture is unavailable.
        """
        try:
            sct = self._get_sct()
            # monitor 1 is usually the primary monitor in mss
            monitors = sct.monitors
            mon = monitors[monitor_idx] if len(monitors) > monitor_idx else monitors[0]
            sct_img = sct.grab(mon)
            # Convert mss BGRA raw bytes to PIL Image (RGB)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            return img
        except Exception as e:
            # Fallback to simulated desktop workspace if display server is unreachable
            return self.generate_mock_scene(VisualSceneType.DESKTOP_GENERAL.value)

    def generate_mock_scene(self, scene_type: str, width: int = 640, height: int = 360) -> Image.Image:
        """
        Generates visually distinct simulated game and media screens
        for testing, demonstrations, and offline simulation.
        """
        img = Image.new("RGB", (width, height), color=(20, 24, 35))
        draw = ImageDraw.Draw(img)

        if scene_type == VisualSceneType.MINECRAFT_DEFEAT.value:
            # 1. Minecraft "You Died!" Screen (Deep Red Vignette + Text)
            # Red gradient background
            for y in range(height):
                alpha = int(100 + (y / height) * 110)
                draw.line([(0, y), (width, y)], fill=(alpha, 15, 20))
            
            # Big "You Died!" headline
            draw.rectangle([width * 0.15, height * 0.25, width * 0.85, height * 0.45], fill=(30, 0, 5, 200), outline=(220, 20, 30), width=2)
            draw.text((width * 0.36, height * 0.32), "YOU DIED!", fill=(255, 255, 255))
            draw.text((width * 0.30, height * 0.48), "Score: 1,420 (Fell from a high place)", fill=(255, 200, 200))
            
            # Respawn buttons
            draw.rectangle([width * 0.28, height * 0.62, width * 0.72, height * 0.72], fill=(60, 60, 65), outline=(180, 180, 190), width=2)
            draw.text((width * 0.45, height * 0.65), "Respawn", fill=(255, 255, 255))

            draw.rectangle([width * 0.28, height * 0.76, width * 0.72, height * 0.86], fill=(60, 60, 65), outline=(180, 180, 190), width=2)
            draw.text((width * 0.42, height * 0.79), "Title Screen", fill=(220, 220, 230))

        elif scene_type == VisualSceneType.MINECRAFT_DIAMOND.value:
            # 2. Minecraft Deepslate Cave with Diamond Vein
            # Dark cave walls
            draw.rectangle([0, 0, width, height], fill=(28, 30, 35))
            # Rough stone patches
            for x, y, r in [(100, 80, 60), (450, 120, 90), (220, 200, 70)]:
                draw.ellipse([x - r, y - r, x + r, y + r], fill=(42, 45, 52))

            # Diamond Ore Blocks (Cyan Glowing Squares)
            ore_positions = [(280, 150), (330, 140), (310, 190), (360, 185)]
            for ox, oy in ore_positions:
                draw.rectangle([ox, oy, ox + 45, oy + 45], fill=(50, 55, 65), outline=(0, 235, 255), width=3)
                # Cyan gem flecks inside
                draw.rectangle([ox + 8, oy + 8, ox + 18, oy + 18], fill=(0, 240, 255))
                draw.rectangle([ox + 25, oy + 22, ox + 36, oy + 34], fill=(0, 255, 230))

            # Crosshair & Light Level HUD
            cx, cy = width // 2, height // 2
            draw.line([(cx - 8, cy), (cx + 8, cy)], fill=(255, 255, 255), width=2)
            draw.line([(cx, cy - 8), (cx, cy + 8)], fill=(255, 255, 255), width=2)
            draw.text((20, 20), "Minecraft 1.20 | Y: -58 | Light: 4 (Diamond Vein Found)", fill=(0, 240, 255))

        elif scene_type == VisualSceneType.MINECRAFT_PLAYING.value:
            # 3. Active Minecraft Gameplay (Sky + Grass Horizon + Hotbar)
            # Blue Sky
            draw.rectangle([0, 0, width, int(height * 0.55)], fill=(110, 165, 245))
            # Green Grass Hills
            draw.rectangle([0, int(height * 0.55), width, height], fill=(68, 140, 45))
            # Oak Tree Trunk and Leaves
            draw.rectangle([int(width * 0.75), int(height * 0.35), int(width * 0.82), int(height * 0.65)], fill=(90, 60, 35))
            draw.rectangle([int(width * 0.70), int(height * 0.18), int(width * 0.87), int(height * 0.38)], fill=(34, 105, 28))

            # Hearts & Hunger HUD
            for i in range(10):
                # Red Hearts
                hx = int(width * 0.28) + (i * 14)
                draw.rectangle([hx, int(height * 0.84), hx + 10, int(height * 0.87)], fill=(220, 20, 40))
                # Hunger Drumsticks
                dx = int(width * 0.70) - (i * 14)
                draw.rectangle([dx, int(height * 0.84), dx + 10, int(height * 0.87)], fill=(180, 110, 40))

            # Hotbar (9 slots)
            bar_w = 260
            bx = (width - bar_w) // 2
            by = int(height * 0.89)
            draw.rectangle([bx, by, bx + bar_w, by + 30], fill=(45, 45, 50), outline=(160, 160, 170), width=2)
            for s in range(9):
                draw.rectangle([bx + (s * 29), by, bx + (s * 29) + 26, by + 28], fill=(60, 60, 65))
            # Active selected slot (Slot 1: Diamond Sword)
            draw.rectangle([bx, by - 2, bx + 28, by + 30], outline=(255, 255, 255), width=2)
            draw.text((20, 20), "Minecraft Server [Survival Mode] | Health: 20/20", fill=(255, 255, 255))

        elif scene_type in (VisualSceneType.CHESS_MATCH.value, VisualSceneType.CHESS_GAMEOVER.value):
            # 4. Chess Board (Checkered Grid)
            draw.rectangle([0, 0, width, height], fill=(30, 32, 40))
            board_sz = int(height * 0.75)
            ox = (width - board_sz) // 2
            oy = int(height * 0.12)
            sq_sz = board_sz // 8

            for r in range(8):
                for c in range(8):
                    color = (235, 215, 185) if (r + c) % 2 == 0 else (145, 95, 60)
                    draw.rectangle([ox + c * sq_sz, oy + r * sq_sz, ox + (c + 1) * sq_sz, oy + (r + 1) * sq_sz], fill=color)

            # Simulated pieces (circles with dots)
            for r, c, col in [(0, 4, (40, 40, 40)), (7, 4, (240, 240, 240)), (3, 3, (240, 240, 240)), (2, 5, (40, 40, 40))]:
                px = ox + c * sq_sz + sq_sz // 2
                py = oy + r * sq_sz + sq_sz // 2
                draw.ellipse([px - 12, py - 12, px + 12, py + 12], fill=col, outline=(100, 100, 100))

            if scene_type == VisualSceneType.CHESS_GAMEOVER.value:
                # Banner Skakmat / Victory
                draw.rectangle([width * 0.15, height * 0.38, width * 0.85, height * 0.62], fill=(20, 20, 25, 230), outline=(234, 179, 8), width=3)
                draw.text((width * 0.34, height * 0.44), "CHECKMATE! 1 - 0", fill=(255, 215, 0))
                draw.text((width * 0.32, height * 0.52), "Winner: Eve Maybe (AI Idol)", fill=(240, 240, 245))
            else:
                draw.text((ox, oy - 22), "Chess Match - Turn: White | ELO: 1450 vs 1500", fill=(220, 220, 230))

        elif scene_type == VisualSceneType.VIDEO_WATCHING.value:
            # 5. YouTube / Stream Video Watching Screen
            draw.rectangle([0, 0, width, height], fill=(15, 15, 20))
            # Video Frame
            draw.rectangle([int(width * 0.05), int(height * 0.08), int(width * 0.95), int(height * 0.85)], fill=(25, 30, 45), outline=(60, 70, 90))
            
            # Animated cat clip in video
            draw.ellipse([int(width * 0.45), int(height * 0.38), int(width * 0.55), int(height * 0.55)], fill=(240, 160, 60))
            draw.polygon([(width * 0.46, height * 0.38), (width * 0.49, height * 0.30), (width * 0.51, height * 0.38)], fill=(240, 160, 60))
            draw.polygon([(width * 0.51, height * 0.38), (width * 0.54, height * 0.30), (width * 0.55, height * 0.38)], fill=(240, 160, 60))

            # YouTube Player Red Scrubber Progress Bar
            py = int(height * 0.81)
            draw.line([(int(width * 0.07), py), (int(width * 0.93), py)], fill=(90, 90, 100), width=4)
            draw.line([(int(width * 0.07), py), (int(width * 0.58), py)], fill=(230, 30, 40), width=4)
            draw.ellipse([int(width * 0.575), py - 5, int(width * 0.585), py + 5], fill=(255, 255, 255))
            draw.text((int(width * 0.07), int(height * 0.86)), "▶ 04:20 / 08:35 | Video: Kucing Oren Salto di Karpet", fill=(220, 220, 225))

        else:
            # 6. General Desktop / Code Editor IDE
            draw.rectangle([0, 0, width, height], fill=(24, 26, 32))
            # Editor Title Bar & Tabs
            draw.rectangle([0, 0, width, 32], fill=(32, 35, 45))
            draw.rectangle([10, 5, 120, 28], fill=(42, 46, 58), outline=(60, 65, 80))
            draw.text((22, 11), "engine.py", fill=(140, 200, 255))
            draw.rectangle([130, 5, 240, 28], fill=(28, 30, 38))
            draw.text((142, 11), "index.html", fill=(160, 165, 180))

            # Syntax code lines
            code_lines = [
                ("import", (200, 120, 240), " torch, numpy as np"),
                ("class", (200, 120, 240), " VisualPerceptionEngine:"),
                ("    def", (100, 180, 255), " observe_screen(self, frame):"),
                ("        # Eve is perceiving what you are doing live!", (100, 130, 150), ""),
                ("        features = self.vision_backbone(frame)", (230, 230, 240), ""),
                ("        return features.classify_scene()", (230, 230, 240), "")
            ]
            for idx, (kw, kw_color, rest) in enumerate(code_lines):
                ly = 50 + idx * 24
                draw.text((25, ly), kw, fill=kw_color)
                draw.text((25 + len(kw) * 8 + 4, ly), rest, fill=(220, 225, 235))

        return img

    @staticmethod
    def compute_image_diff(img1: Image.Image, img2: Image.Image) -> float:
        """
        Calculates normalized pixel difference ratio between two images.
        Returns float in [0.0, 1.0].
        """
        if img1 is None or img2 is None:
            return 1.0

        # Downscale to low-res grayscale for blazingly fast diffing
        sz = (64, 36)
        thumb1 = img1.resize(sz).convert("L")
        thumb2 = img2.resize(sz).convert("L")

        bytes1 = thumb1.tobytes()
        bytes2 = thumb2.tobytes()

        total_pixels = len(bytes1)
        if total_pixels == 0:
            return 0.0

        # Sum of absolute pixel difference normalized to 0.0 - 1.0
        abs_diff = sum(abs(b1 - b2) for b1, b2 in zip(bytes1, bytes2))
        return abs_diff / (total_pixels * 255.0)

    @staticmethod
    def to_base64_data_url(img: Image.Image, max_size: Tuple[int, int] = (480, 270), quality: int = 75) -> str:
        """
        Resizes and encodes a PIL Image into a compact JPEG Base64 Data URL.
        """
        clone = img.copy()
        clone.thumbnail(max_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        clone.save(buf, format="JPEG", quality=quality)
        b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64_str}"
