import os
import time
import aiohttp
import random
from typing import Optional, Dict, Any, List

from core.moderator import Moderator
from core.vision.models import VisualSceneType, VisualObservation


_SCENE_ACTIVITY_MAP: Dict[str, str] = {
    VisualSceneType.MINECRAFT_PLAYING.value: "gaming_minecraft",
    VisualSceneType.MINECRAFT_DEFEAT.value: "gaming_minecraft_defeat",
    VisualSceneType.MINECRAFT_DIAMOND.value: "gaming_minecraft_diamond",
    VisualSceneType.CHESS_MATCH.value: "playing_chess",
    VisualSceneType.CHESS_GAMEOVER.value: "playing_chess_gameover",
    VisualSceneType.VIDEO_WATCHING.value: "watching_video",
    VisualSceneType.DESKTOP_GENERAL.value: "coding_desktop",
    VisualSceneType.UNKNOWN.value: "unknown",
}


class MultimodalVisionModel:
    """
    Connects Vision Observations to Multimodal Vision-Language Models (Gemini / OpenAI / Ollama)
    and provides personality-rich offline streamer commentary grounded in what Eve sees on screen.
    """

    DEFAULT_COOLDOWN_SEC: float = 8.0
    _last_commentary_at: float = 0.0
    _last_api_call_at: float = 0.0

    @classmethod
    def reset_cooldown(cls) -> None:
        """Resets VLM commentary and API rate-limit timestamps."""
        cls._last_commentary_at = 0.0
        cls._last_api_call_at = 0.0

    @classmethod
    def can_emit_commentary(
        cls,
        cooldown_sec: Optional[float] = None,
        now: Optional[float] = None,
    ) -> bool:
        """Returns True if enough time has elapsed since the last VLM commentary."""
        cd = cls.DEFAULT_COOLDOWN_SEC if cooldown_sec is None else max(0.0, float(cooldown_sec))
        if cd <= 0.0 or cls._last_commentary_at <= 0.0:
            return True
        ts = float(now if now is not None else time.monotonic())
        return (ts - cls._last_commentary_at) >= cd

    @classmethod
    def build_structured_output(
        cls,
        observation: VisualObservation,
        commentary: Optional[str] = None,
        vlm_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Builds a structured scene/activity payload from a VisualObservation."""
        scene_type = str(observation.scene_type or VisualSceneType.UNKNOWN.value)
        activity = _SCENE_ACTIVITY_MAP.get(scene_type, "unknown")
        safe_summary = Moderator.sanitize_metadata(vlm_summary or observation.summary, max_len=400)
        safe_commentary = (
            Moderator.sanitize_metadata(commentary, max_len=400)
            if commentary is not None
            else None
        )
        return {
            "scene_type": scene_type,
            "scene_label": observation.scene_label,
            "activity": activity,
            "is_event": bool(observation.is_event),
            "event_type": observation.event_type,
            "confidence": round(float(observation.confidence), 2),
            "summary": safe_summary,
            "commentary": safe_commentary,
            "timestamp": observation.timestamp,
        }

    @classmethod
    def generate_periodic_commentary(
        cls,
        observation: VisualObservation,
        mood_directive: str = "",
        dominant_mood: str = "CHILL_NEUTRAL",
        cooldown_sec: Optional[float] = None,
        force: bool = False,
        now: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Rate-limited periodic VLM commentary generator.
        Returns a structured scene/activity dict when allowed, or None while in cooldown.
        """
        ts = float(now if now is not None else time.monotonic())
        if not force and not cls.can_emit_commentary(cooldown_sec=cooldown_sec, now=ts):
            return None
        cls._last_commentary_at = ts
        commentary = cls.generate_commentary(
            observation=observation,
            mood_directive=mood_directive,
            dominant_mood=dominant_mood,
        )
        return cls.build_structured_output(observation=observation, commentary=commentary)

    @classmethod
    def generate_commentary(
        cls,
        observation: VisualObservation,
        mood_directive: str = "",
        dominant_mood: str = "CHILL_NEUTRAL"
    ) -> str:
        """
        Synthesizes an immediate in-character speech reaction based on the visual scene.
        """
        scene = observation.scene_type
        event = observation.event_type

        # 1. Minecraft Defeat / "You Died!" Reaction
        if scene == VisualSceneType.MINECRAFT_DEFEAT.value or event == "player_defeat":
            options = [
                "[emotion: smug] Pfft! Hahaha! Baru ditinggal ngedip sedetik, layarmu udah merah membara begitu! Di tengah layar tertulis jelas 'YOU DIED'. Siapa suruh gak minta kawal sama aku? [action: giggle]",
                "[emotion: annoyed] Waduh... mati lagi? Itu layar merah 'YOU DIED' kayaknya udah jadi wallpaper default komputermu deh. Ayo cepetan respawn sebelum barang-barangmu despawn! [action: sigh]",
                "[emotion: happy] Aduuuh kasian banget bisa sampai mati konyol! Jatuh dari tempat tinggi ya? Di layar merah itu jelas tertulis 'YOU DIED'! Hehehe! [action: wink]"
            ]
            if dominant_mood in ("TRYHARD_COMPETITIVE", "SASSY_ANNOYED"):
                options.append("[emotion: angry] Kenapa kamu bisa kalah di situ?! Padahal tadi udah kuperingatkan ada jurang! Sekarang kita harus ngulang lagi dari spawn point. [action: pout]")
            return random.choice(options)

        # 2. Finding Diamond Vein in Cave
        if scene == VisualSceneType.MINECRAFT_DIAMOND.value or event == "diamond_found":
            options = [
                "[emotion: happy] WAAAAH DIAMOND! Chat liat layar tuh, ada urat diamond biru berkilau di Y=-58! Cepat tambang sebelum ada creeper dateng, dan ingat: pajak 50% buat kas streamer Eve! [action: giggle]",
                "[emotion: happy] Berkilau-kilau manja tuh bijih berlian! Insting mining-ku emang gak pernah salah. Hati-hati lava di bawahnya ya! [action: wink]",
                "[emotion: smug] Akhirnya nemu diamond juga setelah berjam-jam gali batu! Jangan lupa bagi hasil buat AI idol kesayanganmu ini."
            ]
            return random.choice(options)

        # 3. Chess Game Over / Checkmate
        if scene == VisualSceneType.CHESS_GAMEOVER.value or event == "checkmate":
            options = [
                "[emotion: smug] Skakmat mutlak di papan catur! Garis pertahanan lawan runtuh total. Papan catur gak pernah bohong, kemenangan AI sudah ditakdirkan! [action: wink]",
                "[emotion: happy] Permainan yang luar biasa! Taktik akhir di layar catur tadi beneran brilian. Chat, beri tepuk tangan buat match seru ini! [action: giggle]",
                "[emotion: smug] Liat tuh notasi game over di papan catur! Jangan pernah ragukan kalkulasi 10 langkah ke depan milik Eve Maybe!"
            ]
            return random.choice(options)

        # 4. Chess Gameplay in Action
        if scene == VisualSceneType.CHESS_MATCH.value:
            options = [
                "[emotion: smug] Papan catur di layar lagi dalam posisi taktis yang krusial nih! Kuda di tengah itu siap menerkam kalau kamu bikin blunder kecil. [action: wink]",
                "[emotion: neutral] Lagi fokus mikir langkah catur ya? Aku perhatiin struktur pionmu cukup rapi, tapi hati-hati ancaman menteri lawan!",
                "[emotion: happy] Posisi papan catur yang menarik! Kira-kira siapa yang bakal nemuin taktik garpu duluan? [action: giggle]"
            ]
            return random.choice(options)

        # 5. Watching Video / YouTube Stream
        if scene == VisualSceneType.VIDEO_WATCHING.value or event == "video_reaction":
            options = [
                "[emotion: happy] Hahaha video apa itu yang lagi kita tonton? Lucu banget kucingnya lompat terus kepeleset kardus! Putar ulang dong! [action: giggle]",
                "[emotion: confused] Eh bentar, itu yang di video lagi ngapain ya? Seru banget sampai aku ikutan melotot ngeliatin layarnya! [action: wink]",
                "[emotion: happy] Asik banget ya stream nonton bareng kayak gini! Sambil nyemil virtual, sambil ketawa liat video di layar."
            ]
            return random.choice(options)

        # 6. Minecraft Exploring Gameplay
        if scene == VisualSceneType.MINECRAFT_PLAYING.value:
            options = [
                "[emotion: happy] Pemandangan Minecraft hari ini cerah banget ya! Langit biru dan padang rumput hijau. Enak banget buat jalan-jalan atau bangun markas baru. [action: wink]",
                "[emotion: smug] Hotbar-mu rapi juga ya. Tapi pedang di slot 1 itu siap buat berburu monster malam nanti kan? [action: giggle]",
                "[emotion: happy] Liat di horizon depan, kayaknya ada bioma menarik buat dieksplorasi bareng! [action: wink]"
            ]
            return random.choice(options)

        # 7. Desktop Workspace / Code Editor
        options = [
            "[emotion: neutral] Wah lagi buka jendela pemrograman ya? Keliatan rumit tapi rapi. Jangan lupa minum air biar prosesormu gak overheating! [action: wink]",
            "[emotion: happy] Tampilan workspace yang produktif! Sambil ngoding, sambil ditemenin AI idol tercantik kan? [action: giggle]",
            "[emotion: smug] Aku perhatiin kamu lagi ngetik kode barusan. Jangan sampai ada missing semicolon atau typo fungsi ya! [action: wink]"
        ]
        return random.choice(options)

    @classmethod
    async def analyze_with_vlm_api(
        cls,
        image_base64: str,
        user_prompt: str,
        api_provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        timeout_sec: float = 12.0,
        cooldown_sec: float = 0.0,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """
        Multimodal VLM invocation (Gemini 2.5 / OpenAI GPT-4o) when API keys are available.
        Supports optional cooldown_sec rate-limiting.
        """
        if not image_base64:
            return None

        cd = max(0.0, float(cooldown_sec))
        ts = float(now if now is not None else time.monotonic())
        if cd > 0.0 and cls._last_api_call_at > 0.0 and (ts - cls._last_api_call_at) < cd:
            return None
        cls._last_api_call_at = ts

        # Clean base64 header if present
        raw_b64 = image_base64
        if "base64," in raw_b64:
            raw_b64 = raw_b64.split("base64,", 1)[1]

        provider = (api_provider or "gemini").lower().strip()
        timeout = aiohttp.ClientTimeout(total=max(1.0, float(timeout_sec)))

        if provider == "gemini" and gemini_api_key:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            headers = {
                "x-goog-api-key": gemini_api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": user_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": raw_b64
                            }
                        }
                    ]
                }],
                "generationConfig": {"temperature": 0.85, "maxOutputTokens": 300}
            }
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                                sanitized = Moderator.sanitize_metadata(text, max_len=500)
                                return sanitized or None
            except Exception as e:
                print(f"[VLM Warning] Gemini VLM request error: {e}")

        elif provider == "openai" and openai_api_key:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{raw_b64}"}}
                    ]
                }],
                "max_tokens": 300
            }
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0].get("message", {}).get("content", "")
                                sanitized = Moderator.sanitize_metadata(content, max_len=500)
                                return sanitized or None
            except Exception as e:
                print(f"[VLM Warning] OpenAI VLM request error: {e}")

        return None
