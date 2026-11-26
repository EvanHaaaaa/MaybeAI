import asyncio
import inspect
import json
import random
import time
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Tuple

from core.desktop.obs_client import DEFAULT_SCENE_MAP
from core.performance.models import (
    PerformanceStatus,
    SongMoodCategory,
    StageMovement,
    ChoreographyStep,
    SetlistItem,
    PerformanceSession
)


class PerformanceDirector:
    """
    Dynamic Performance Director for Eve Maybe (AI Idol Engine).
    Autonomously plans stage setlists, selects songs matching emotional mood,
    choreographs multi-section avatar gestures/expressions/lighting per lyric line,
    leads pre-show and post-show MC crowd engagement, and tracks audience glowstick cheers.
    """

    def __init__(
        self,
        songs_config_path: str = "config/songs.json",
        storage_path: Optional[str] = None,
        second_brain_dir: str = "data/second_brain",
        data_dir: Optional[str] = None,
        scene_switcher: Optional[Callable[[str, str], Any]] = None,
        scene_map: Optional[Dict[str, str]] = None,
    ):
        self.songs_config_path = Path(songs_config_path)
        self.songs_catalog: Dict[str, Any] = {}
        self.load_songs_catalog()
        self.scene_switcher = scene_switcher
        self.scene_map: Dict[str, str] = dict(DEFAULT_SCENE_MAP)
        if scene_map:
            for k, v in scene_map.items():
                if v:
                    self.scene_map[str(k).strip().lower()] = str(v).strip()

        if storage_path is None:
            if data_dir:
                storage_path = str(Path(data_dir) / "director.json")
            else:
                storage_path = "data/performance/director.json"

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if data_dir and second_brain_dir == "data/second_brain":
            self.second_brain_dir = Path(data_dir) / "second_brain"
        else:
            self.second_brain_dir = Path(second_brain_dir)

        self.session: PerformanceSession = PerformanceSession()
        self.concert_history: List[Dict[str, Any]] = []

        self._load_or_seed()
        self.sync_to_second_brain()

    def load_songs_catalog(self):
        if self.songs_config_path.exists():
            try:
                with open(self.songs_config_path, "r", encoding="utf-8") as f:
                    self.songs_catalog = json.load(f)
            except Exception as e:
                print(f"[PerformanceDirector] Error loading songs catalog: {e}")

    def _load_or_seed(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "active_session" in data and data["active_session"]:
                        self.session = PerformanceSession.from_dict(data["active_session"])
                    self.concert_history = data.get("history", [])
            except Exception as e:
                print(f"[PerformanceDirector] Error loading director data: {e}")
                self._seed_default_state()
        else:
            self._seed_default_state()
        self.save()

    def _seed_default_state(self):
        self.session = PerformanceSession(
            status=PerformanceStatus.IDLE.value,
            current_song_id="digital_world",
            current_title="Digital World",
            dominant_mood="HYPE_EXCITED",
            mood_reason="Eve bersemangat menyapa para penonton!",
            audience_glowsticks=50,
            performance_score=95
        )
        self.plan_concert_setlist("Konser Idol Virtual Pertama")
        self.concert_history = [
            {
                "concert_title": "Grand Debut Showcase",
                "song_id": "digital_world",
                "title": "Digital World",
                "score": 96,
                "glowsticks": 120,
                "completed_at": time.strftime("%Y-%m-%d")
            }
        ]

    def save(self):
        try:
            data = {
                "active_session": self.session.to_dict(),
                "history": self.concert_history
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[PerformanceDirector] Error saving director state: {e}")

    # --- Autonomous Song & Setlist Curation ---
    def get_autonomous_song_recommendation(
        self,
        dominant_mood: str = "HYPE_EXCITED",
        current_morale: int = 100
    ) -> Tuple[str, str]:
        """
        Autonomously selects the best song from the catalog based on
        Eve's active emotional state and stream atmosphere.
        """
        mood_clean = dominant_mood.upper()

        if mood_clean == "HYPE_EXCITED":
            chosen = "digital_world"
            reason = "Energi stream lagi meluap-luap dan penuh hype! Lagu cyber-pop ini sempurna buat bakar semangat chat!"
        elif mood_clean == "CURIOUS_PENSIVE":
            chosen = "midnight_starlight"
            reason = "Suasana malam lagi tenang dan reflektif. Saatnya alunan ballad lofi yang menenangkan."
        elif mood_clean == "TRYHARD_COMPETITIVE":
            chosen = "glitch_overclock"
            reason = "Adrenalin kompetitif 100%! Eve mau pamer vokal tempo kilat dan sirkuit overclocking!"
        elif mood_clean == "SASSY_ANNOYED":
            chosen = "tsundere_anthem"
            reason = "Lagi agak gemas sama tingkah chat, lagu tsundere ini cocok buat ngeledek sambil tetap imut!"
        else:
            chosen = "minecraft_creeper_lullaby"
            reason = "Pilihan santai khas streamer gamer buat menghibur penonton!"

        # Fallback if song not in catalog
        if chosen not in self.songs_catalog:
            chosen = next(iter(self.songs_catalog.keys()), "digital_world")

        return chosen, reason

    def plan_concert_setlist(self, setlist_title: Optional[str] = None) -> List[SetlistItem]:
        """Arranges an entire balanced idol concert setlist."""
        items: List[SetlistItem] = []

        sequence = [
            ("digital_world", "Lagu Pembuka: Membakar antusiasme penonton dengan cyber-pop banger."),
            ("midnight_starlight", "Lagu Kedua: Intermisi emosional yang syahdu dan hangat."),
            ("glitch_overclock", "Klimaks Konser: Ledakan tempo cepat dan vokal intens."),
            ("tsundere_anthem", "Encore Pamungkas: Penutup manis penuh godaan buat chat tercinta!")
        ]

        for order, (s_id, reason) in enumerate(sequence, start=1):
            s_info = self.songs_catalog.get(s_id, {})
            items.append(
                SetlistItem(
                    order=order,
                    song_id=s_id,
                    title=s_info.get("title", s_id),
                    mood_category=s_info.get("mood_category", "hype_energetic"),
                    status="current" if order == 1 else "queued",
                    reason=reason
                )
            )

        self.session.setlist = items
        self.session.updated_at = time.time()
        self.save()
        self.sync_to_second_brain()
        return items

    def _notify_scene_switch(self, scene_name: str, reason: str) -> None:
        """Invokes optional scene_switcher callback (sync or async) without blocking or raising."""
        if not self.scene_switcher:
            return
        try:
            res = self.scene_switcher(scene_name, reason)
            if inspect.isawaitable(res):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(res)
                except RuntimeError:
                    asyncio.run(res)
        except Exception as exc:
            print(f"[PerformanceDirector] scene_switcher error: {exc}")

    # --- Performance Execution & Choreography ---
    def start_performance(
        self,
        song_id: Optional[str] = None,
        dominant_mood: str = "HYPE_EXCITED",
        dedication_user: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Prepares stage, choreographs opening MC banter, and returns (song_id, pre_show_mc_speech).
        """
        if not song_id:
            s_id, mood_reason = self.get_autonomous_song_recommendation(dominant_mood)
        else:
            s_id = song_id
            mood_reason = f"Dipilih khusus untuk penonton tercinta!"

        song_data = self.songs_catalog.get(s_id, {})
        title = song_data.get("title", s_id)

        self.session.current_song_id = s_id
        self.session.current_title = title
        self.session.dominant_mood = dominant_mood
        self.session.mood_reason = mood_reason
        self.session.status = PerformanceStatus.MC_INTRO.value
        self.session.current_section = "intro"

        # Update setlist status
        for item in self.session.setlist:
            if item.song_id == s_id:
                item.status = "current"
            elif item.status == "current":
                item.status = "completed"

        # Craft bespoke pre-show MC banter
        user_mention = f"khususnya buat {dedication_user} " if dedication_user and dedication_user not in ("Chat", "System", "User") else ""
        default_intro = song_data.get("intro_dialogue", f"Halo semuanya! Eve siap menyanyikan {title} buat kalian!")
        mc_speech = (
            f"[emotion: excited] 🎤 PERTUNJUKAN SPESIAL DIMULAI! [action: wink] "
            f"Karena mood Eve lagi **{dominant_mood}**, Eve memilih lagu spesial: **{title}**! "
            f"Penampilan ini Eve persembahkan {user_mention}dan seluruh chat! "
            f"{default_intro} Ayo nyalakan glowstick kalian dengan '!glowstick' di chat!"
        )

        self.session.last_mc_intro = mc_speech
        self.session.updated_at = time.time()
        self.save()
        self._notify_scene_switch(
            self.scene_map.get("performance", "Karaoke Stage"),
            f"Starting performance: {title}",
        )
        return s_id, mc_speech

    def get_choreography_step_for_line(self, song_id: str, line_idx: int) -> ChoreographyStep:
        """Determines the synchronized avatar movement, emotion, lighting, and action for a line."""
        song = self.songs_catalog.get(song_id, {})
        lyrics = song.get("lyrics", [])

        if 0 <= line_idx < len(lyrics):
            line_data = lyrics[line_idx]
            section = line_data.get("section", "verse")
            emotion = line_data.get("emotion", "happy")
            movement = line_data.get("movement", StageMovement.SWAY_LEFT.value)
            lighting = line_data.get("stage_lighting", "neon_cyan")

            # Determine action based on emotion/section
            if section == "chorus":
                action = "giggle" if emotion == "blush" else "wink"
            elif section == "pre_chorus":
                action = "nod"
            elif section == "drop":
                action = "gasp"
            else:
                action = "tilt"

            # Occasional crowd callout during pre-chorus or chorus
            callout = None
            if section == "pre_chorus":
                callouts = ["Mana glowstick-nya chat?!", "Ayo goyang bareng Eve!", "Semuanya bersuara!"]
                callout = random.choice(callouts)

            step = ChoreographyStep(
                section=section,
                emotion=emotion,
                action=action,
                movement=movement,
                stage_lighting=lighting,
                crowd_callout=callout
            )
        else:
            step = ChoreographyStep(section="outro", emotion="happy", movement="bow", stage_lighting="golden_glow")

        self.session.current_step = step
        self.session.current_section = step.section
        self.session.status = PerformanceStatus.PERFORMING.value
        return step

    def record_audience_cheer(self, user: str, cheer_type: str = "glowstick") -> int:
        """Records chat participation (glowstick, clap, cheer) during song."""
        self.session.audience_glowsticks += 1
        entry = {
            "user": user,
            "type": cheer_type,
            "time": time.strftime("%H:%M:%S")
        }
        self.session.cheers_history.append(entry)
        self.session.updated_at = time.time()
        return self.session.audience_glowsticks

    def finish_performance(self) -> Tuple[str, int]:
        """
        Concludes performance, calculates Eve's self-rating out of 100,
        generates post-show banter, advances setlist, and syncs to Second Brain.
        """
        s_id = self.session.current_song_id or "digital_world"
        song_data = self.songs_catalog.get(s_id, {})
        title = song_data.get("title", s_id)

        # Self-rating: 88-99 based on glowsticks count
        bonus = min(10, self.session.audience_glowsticks // 10)
        score = random.randint(88, 92) + bonus
        score = min(100, max(85, score))
        self.session.performance_score = score
        self.session.total_shows_completed += 1
        self.session.status = PerformanceStatus.MC_OUTRO.value

        # Mark setlist item as completed
        for item in self.session.setlist:
            if item.song_id == s_id:
                item.status = "completed"

        default_outro = song_data.get("outro_dialogue", "Terima kasih sudah mendengarkan nyanyianku!")
        outro_speech = (
            f"[emotion: happy] 💖 PERFORMANCE SELESAI! [action: bow] "
            f"Kalian semua luar biasa! {self.session.audience_glowsticks} glowstick menyala di panggung hari ini! "
            f"Penampilan barusan Eve beri nilai **{score}/100**! "
            f"{default_outro} Kalau kalian pengen lagu tambahan, spam 'ENCORE' di chat ya!"
        )

        self.session.last_mc_outro = outro_speech

        # Archive
        self.concert_history.insert(0, {
            "concert_title": f"Live Showcase: {title}",
            "song_id": s_id,
            "title": title,
            "score": score,
            "glowsticks": self.session.audience_glowsticks,
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        self.save()
        self.sync_to_second_brain()
        self._notify_scene_switch(
            self.scene_map.get("social", "Just Chatting"),
            f"Finished performance: {title} (score {score}/100)",
        )
        return outro_speech, score

    # --- Second Brain Markdown Sync ---
    def sync_to_second_brain(self):
        try:
            p_dir = self.second_brain_dir / "performance"
            p_dir.mkdir(parents=True, exist_ok=True)
            f_path = p_dir / "setlist.md"

            lines = [
                "# 🎤 Dynamic Performance Director & Idol Concert Setlist",
                f"> Last synchronized: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## 🌟 Active Stage Status",
                f"- **Stage Status**: `{self.session.status.upper()}`",
                f"- **Current Song**: `{self.session.current_title or 'None'}` (`{self.session.current_song_id}`)",
                f"- **Dominant Mood**: `{self.session.dominant_mood}`",
                f"- **Curation Reason**: *\"{self.session.mood_reason}\"*",
                f"- **Audience Glowsticks**: ✨ {self.session.audience_glowsticks} cheers",
                f"- **Latest Performance Score**: 🏆 {self.session.performance_score}/100",
                "",
                "## 📋 Live Concert Setlist",
                "| Order | Song Title | Genre / Vibe | Status | Curation Reasoning |",
                "|:-----:|:-----------|:------------:|:------:|:--------------------|"
            ]

            for it in self.session.setlist:
                status_icon = "🟢 Now Playing" if it.status == "current" else ("✅ Completed" if it.status == "completed" else "⏳ Queued")
                lines.append(f"| #{it.order} | **{it.title}** | `{it.mood_category}` | {status_icon} | {it.reason} |")

            lines.append("")
            lines.append("## 🏆 Past Showcase History")
            lines.append("| Date | Showcase | Song | Score | Glowsticks |")
            lines.append("|:-----|:---------|:-----|:-----:|:----------:|")
            for h in self.concert_history[:8]:
                lines.append(f"| {h.get('completed_at', '-')} | **{h.get('concert_title', '')}** | {h.get('title', '')} | {h.get('score', 90)}/100 | ✨ {h.get('glowsticks', 0)} |")

            f_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"[PerformanceDirector] Error syncing Second Brain setlist: {e}")

    # --- System Prompt Directive ---
    def get_prompt_directive(self) -> str:
        s_title = self.session.current_title or "Digital World"
        st = self.session.status.upper()

        if self.session.status == PerformanceStatus.IDLE.value:
            return (
                "[🎤 DYNAMIC PERFORMANCE DIRECTOR & IDOL ENGINE]\n"
                "Stage Status: IDLE (Standby panggung).\n"
                f"You are a charismatic, autonomous AI Idol performer! You don't just wait for !sing commands.\n"
                f"You curate songs matching your emotional state ({self.session.dominant_mood}), arrange setlists, and interact with audience glowsticks!"
            )

        return (
            f"[🎤 LIVE STAGE PERFORMANCE: {s_title.upper()}]\n"
            f"You are on stage as an autonomous AI Idol performer!\n"
            f"- Stage Status: {st}\n"
            f"- Current Song: {s_title}\n"
            f"- Section: {self.session.current_section.upper()}\n"
            f"- Mood Curation: {self.session.mood_reason}\n"
            f"- Audience Glowsticks: {self.session.audience_glowsticks} ✨\n\n"
            "STAGE DIRECTIVES:\n"
            "1. Radiate passionate idol charisma! Encourage chatters to wave glowsticks and sing along.\n"
            "2. Adapt expressions and gestures to song sections (gentle in verses, high-energy blush/sparkle in chorus).\n"
            "3. If chat requests an encore, respond with adorable tsundere gratitude!"
        )

    # --- Unified State ---
    def get_state(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "available_songs": [
                {
                    "id": k,
                    "title": v.get("title", k),
                    "artist": v.get("artist", "Eve Maybe"),
                    "mood_category": v.get("mood_category", "hype_energetic"),
                    "recommended_moods": v.get("recommended_moods", [])
                }
                for k, v in self.songs_catalog.items()
            ],
            "concert_history": self.concert_history[:8]
        }
