import os
import aiohttp
import random
from typing import Optional, Dict, Any, List

from core.vision.models import VisualSceneType, VisualObservation


class MultimodalVisionModel:
    """
    Connects Vision Observations to Multimodal Vision-Language Models (Gemini / OpenAI / Ollama)
    and provides personality-rich offline streamer commentary grounded in what Eve sees on screen.
    """

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
        openai_api_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Multimodal VLM invocation (Gemini 2.5 / OpenAI GPT-4o) when API keys are available.
        """
        # Clean base64 header if present
        raw_b64 = image_base64
        if "base64," in raw_b64:
            raw_b64 = raw_b64.split("base64,")[1]

        if api_provider == "gemini" and gemini_api_key:
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
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                return "".join(p.get("text", "") for p in parts if "text" in p).strip()
            except Exception as e:
                print(f"[VLM Warning] Gemini VLM request error: {e}")

        elif api_provider == "openai" and openai_api_key:
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
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"[VLM Warning] OpenAI VLM request error: {e}")

        return None
