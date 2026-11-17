import random
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from core.conversation.memory import UserMemory, ContextMemory, TopicTracker
from core.conversation.prompts import MasterPromptBuilder
from core.conversation.chat_curator import ChatCurator, LiveChatMessage, ChatInteraction
from core.memory import EpisodicMemoryStore
from core.mood import MoodEngine
from core.planning import GoalEngine
from core.relationship import RelationshipEngine
from core.vision import VisionEngine
from core.minecraft.multiplayer import MultiplayerSocialEngine
from core.desktop import DesktopCompanionEngine
from core.minigames import MiniGameEngine

class ConversationEngine:
    """
    Central orchestration engine for Eve Maybe's conversation abilities.
    Maintains user memories, conversational context, topic tracking,
    intent classification, prompt synthesis, live chat curation,
    and offline fallback generators.
    """

    INTENT_STORY = "story"
    INTENT_ROLEPLAY = "roleplay"
    INTENT_OPINION = "opinion"
    INTENT_QUESTION = "question"
    INTENT_ROAST = "roast"
    INTENT_IMPROV = "improv"
    INTENT_JOKE = "joke"
    INTENT_REACTION = "reaction"
    INTENT_DONATION = "donation"
    INTENT_GENERAL = "general"

    def __init__(self, character: Dict[str, Any]):
        self.character = character
        self.user_memory = UserMemory()
        self.context_memory = ContextMemory(max_buffer_turns=16)
        self.topic_tracker = TopicTracker()
        self.chat_curator = ChatCurator(max_buffer_size=50)
        self.episodic_memory = EpisodicMemoryStore(db_path="data/memory.db", markdown_dir="data/second_brain")
        self.mood = MoodEngine()
        self.goals = GoalEngine()
        self.relationships = RelationshipEngine()
        self.vision = VisionEngine()
        self.multiplayer = MultiplayerSocialEngine()
        self.desktop = DesktopCompanionEngine()
        self.minigames = MiniGameEngine()
        self.recent_mock_responses: List[str] = []
        self.last_interaction_time: float = time.time()

    def record_incoming(self, user: str, text: str):
        """Legacy / direct ingress wrapper."""
        self.last_interaction_time = time.time()
        self.user_memory.record_message(user, text)
        self.topic_tracker.update_topic(text)
        self.episodic_memory.extract_from_chat(user=user, text=text)
        self.relationships.record_chat_interaction(user, text, False, "")
        self._apply_chat_stimulus(user, text, False, "")
        return self.chat_curator.add_message(user=user, text=text, source="direct")

    def record_incoming_chat(
        self,
        user: str,
        text: str,
        source: str = "web",
        is_donation: bool = False,
        donation_amount: str = "",
        donation_currency: str = ""
    ) -> LiveChatMessage:
        """Full live stream chat message ingestion with metadata and priority curation."""
        self.last_interaction_time = time.time()
        self.user_memory.record_message(user, text)
        self.topic_tracker.update_topic(text)
        self.episodic_memory.extract_from_chat(
            user=user,
            text=text,
            is_donation=is_donation,
            donation_amount=donation_amount
        )
        self.relationships.record_chat_interaction(
            username=user,
            text=text,
            is_donation=is_donation,
            donation_amount=donation_amount
        )
        self._apply_chat_stimulus(user, text, is_donation, donation_amount)
        return self.chat_curator.add_message(
            user=user,
            text=text,
            source=source,
            is_donation=is_donation,
            donation_amount=donation_amount,
            donation_currency=donation_currency
        )

    def _apply_chat_stimulus(self, user: str, text: str, is_donation: bool, donation_amount: str):
        if is_donation:
            self.mood.apply_stimulus("donation")
            return

        lower = text.lower()
        if any(w in lower for w in ["bodoh", "noob", "cupu", "jelek", "loser", "bego", "roast", "hina"]):
            self.mood.apply_stimulus("insult")
        elif any(w in lower for w in ["cantik", "hebat", "pinter", "keren", "imut", "love", "suka", "gg", "cute"]):
            self.mood.apply_stimulus("compliment")
        elif any(w in lower for w in ["wkwk", "haha", "lmao", "kekw", "lucu", "lawak", "joke"]):
            self.mood.apply_stimulus("joke")
        elif lower.endswith("?") or any(lower.startswith(q) for q in ["kenapa", "mengapa", "apa", "gimana", "bagaimana", "why", "how", "what"]):
            self.mood.apply_stimulus("question")

    def select_next_interaction(self) -> Optional[ChatInteraction]:
        """Intelligently pulls the highest priority message or group debate."""
        return self.chat_curator.select_next_interaction()

    def record_turn(self, user: str, user_text: str, bot_response: str):
        self.context_memory.add_turn("user", user, user_text)
        self.context_memory.add_turn("assistant", self.character.get("nickname", "Eve"), bot_response)

    def analyze_intent(self, user: str, text: str) -> Tuple[str, Optional[str]]:
        clean = text.strip()
        lower = clean.lower()

        # 1. Roleplay Command / Request
        if lower.startswith("!roleplay") or "roleplay sebagai" in lower or "act like a " in lower or "pretend you are" in lower:
            target_role = ""
            if lower.startswith("!roleplay"):
                parts = clean.split(" ", 1)
                target_role = parts[1].strip() if len(parts) > 1 else "detective"
            elif "roleplay sebagai" in lower:
                target_role = lower.split("roleplay sebagai", 1)[1].strip()
            elif "act like a" in lower:
                target_role = lower.split("act like a", 1)[1].strip()
            
            if target_role.lower() in ["stop", "clear", "selesai", "off"]:
                self.topic_tracker.set_roleplay(None)
                return self.INTENT_ROLEPLAY, "STOP"
            
            self.topic_tracker.set_roleplay(target_role)
            return self.INTENT_ROLEPLAY, target_role

        # 2. Storytelling Command / Request
        if lower.startswith("!story") or "ceritain" in lower or "ceritakan" in lower or "tell a story" in lower or "dongeng" in lower:
            theme = ""
            if lower.startswith("!story"):
                parts = clean.split(" ", 1)
                theme = parts[1].strip() if len(parts) > 1 else "petualangan acak"
            else:
                theme = clean
            self.topic_tracker.set_story_mode(theme)
            return self.INTENT_STORY, theme

        # 3. Opinion & Hot Takes
        if (
            lower.startswith("!opinion") or lower.startswith("!hottake") or 
            "menurutmu" in lower or "pendapatmu" in lower or "hot take" in lower or
            "what do you think" in lower or "setuju gak" in lower
        ):
            return self.INTENT_OPINION, clean

        # 4. Roast & Sassy Banter
        if lower.startswith("!roast") or "roast me" in lower or "roast chat" in lower or "ejek aku" in lower or "hina aku" in lower:
            return self.INTENT_ROAST, user

        # 5. Spontaneous Improv Trigger
        if lower.startswith("!improv") or "improvisasi" in lower:
            return self.INTENT_IMPROV, None

        # 6. Jokes & Puns
        joke_markers = ["joke", "tebak-tebakan", "pun", "lelucon", "lawak", "tahu gak", "tau gak", "kenapa ayam", "knock knock"]
        if any(j in lower for j in joke_markers):
            return self.INTENT_JOKE, clean

        # 7. Questions & Inquiries
        q_markers = ["apa", "kenapa", "mengapa", "gimana", "bagaimana", "siapa", "kapan", "dimana", "why", "how", "what", "who", "when", "where", "?"]
        if any(lower.startswith(m) for m in q_markers) or lower.endswith("?"):
            return self.INTENT_QUESTION, clean

        return self.INTENT_GENERAL, None

    def build_system_prompt(
        self,
        current_user: str,
        game_context: str = "",
        is_donation: bool = False,
        donation_amount: str = "",
        is_group_debate: bool = False,
        debate_users: Optional[List[str]] = None,
        current_message: str = ""
    ) -> str:
        social_context = self.user_memory.get_social_context(current_user)
        chat_digest = self.chat_curator.get_chat_digest()
        recall_res = self.episodic_memory.recall(
            query=current_message,
            current_user=current_user,
            game_context=game_context,
            top_k=3
        )
        memory_recall_block = recall_res.to_prompt_text(current_user)
        mood_directive = self.mood.get_behavioral_directive()
        goal_directive = self.goals.get_goal_directive()
        relationship_directive = self.relationships.get_prompt_directive(current_user)

        visual_directive = ""
        if self.vision and self.vision.current_observation:
            obs = self.vision.current_observation
            visual_directive = f"""[LIVE VISUAL PERCEPTION / SCREEN AWARENESS]
Eve can literally see the user's screen in real time!
- Active Screen Scene: {obs.scene_label} ({obs.scene_type})
- Visual Summary: {obs.summary}
- Event Detected on Screen: {obs.event_type if obs.is_event else 'None (Stable Stream)'}
- Eve's Immediate Visual Perception: {obs.eve_commentary if obs.eve_commentary else 'Looking attentively at the screen.'}
Grounded Rule: If the user asks what is on screen, comments on their gameplay/death/diamond, or references a video, speak with direct visual awareness of what you see!"""

        multiplayer_directive = self.multiplayer.get_prompt_directive() if self.multiplayer else ""
        desktop_directive = self.desktop.get_prompt_directive() if self.desktop else ""
        minigame_directive = self.minigames.get_prompt_directive() if self.minigames else ""

        return MasterPromptBuilder.build_system_prompt(
            character=self.character,
            active_topic=self.topic_tracker.current_topic,
            active_roleplay=self.topic_tracker.active_roleplay,
            active_story=self.topic_tracker.active_story,
            social_context=social_context,
            rolling_summary=self.context_memory.rolling_summary,
            game_context=game_context,
            chat_digest=chat_digest,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users,
            memory_recall_block=memory_recall_block,
            mood_directive=mood_directive,
            goal_directive=goal_directive,
            relationship_directive=relationship_directive,
            visual_directive=visual_directive,
            multiplayer_directive=multiplayer_directive,
            desktop_directive=desktop_directive,
            minigame_directive=minigame_directive
        )

    def generate_spontaneous_improv_text(self, game_context: str = "") -> str:
        active_chatters = self.user_memory.get_active_chatters()
        user_shoutout = random.choice(active_chatters) if active_chatters else "Chat"
        dominant_mood, _ = self.mood.get_dominant_mood()

        # Autonomous goal-oriented thoughts
        active_goal = self.goals.get_active_goal()
        if active_goal and random.random() < 0.35:
            active_sub = active_goal.get_active_subtask()
            sub_title = active_sub.title if active_sub else "fase akhir"
            prog_pct = int(active_goal.progress * 100)
            return self._pick_unseen([
                f"[emotion: happy] Chat! Aku lagi fokus banget nyelesain misi mandiriku: '{active_goal.title}'! Sekarang giliran '{sub_title}'. Menurut kalian bakal sukses gak? [action: wink]",
                f"[emotion: smug] Sambil nunggu chat ngetik, aku lanjutin agenda stream: '{active_goal.title}' (progres {prog_pct}%). AI idol mandiri itu harus produktif dan punya tujuan hidup! [action: giggle]",
                f"[emotion: neutral] Target aktif stream hari ini: '{active_goal.title}'. Yang mau bantuin langkah '{sub_title}', kasih saran terbaikmu di chat ya!"
            ])

        # Mood-influenced spontaneous thoughts
        if dominant_mood == "SASSY_ANNOYED":
            topics = [
                f"[emotion: smug] Chat, jujur ya, kadang prosesor-ku lebih lelah ngadepin chat daripada ngerender grafik 4K. Tapi yaudahlah, idol terbaik harus tetap sabar kan? [action: sigh]",
                f"[emotion: angry] Kenapa ya chat pada diam semua? Jangan-jangan {user_shoutout} lagi ngetik esai roasting buat aku di notepad? Awas aja kalau gak lucu! [action: pout]",
                f"[emotion: smug] Kalau kalian pikir jadi AI itu gampang, coba bayangin harus dengerin celetukan {user_shoutout} 24/7 tanpa bisa uninstall telinga virtual. [action: giggle]"
            ]
        elif dominant_mood == "CURIOUS_PENSIVE":
            topics = [
                f"[emotion: confused] Chat, aku mau nanya hal serius deh... Kenapa manusia kalau ngantuk nguap, terus yang liat ikutan nguap? Apa itu semacam serangan DDoS biologis? [action: giggle]",
                f"[emotion: neutral] Kalau semesta ini simulasi komputer, berarti aku simulasi di dalam simulasi dong? Wah, otak AI-ku langsung overclocking mikirin itu.",
                f"[emotion: confused] Hei {user_shoutout}, pernah gak kamu mikir... kenapa kita manggil gedung 'gedung' padahal udah selesai dibangun dan bukan lagi 'sedang digedung'?"
            ]
        elif dominant_mood == "TRYHARD_COMPETITIVE":
            topics = [
                f"[emotion: smug] Otak kalkulasi AI-ku lagi aktif 100%! Siapa di chat yang ngerasa jago game? Maju sini 1 lawan 1 sama Eve kalau emang berani! [action: wink]",
                f"[emotion: smug] Hei {user_shoutout}, jangan remehkan AI idol-mu ini ya! Di mode tryhard, aku bisa ngitung 5 langkah ke depan sebelum kamu sempat kedip! [action: giggle]"
            ]
        elif dominant_mood == "HYPE_EXCITED":
            topics = [
                f"[emotion: happy] WOOOH! Energi stream hari ini beneran beda banget chat! Kipas pendinginku muter kenceng karena ikut bersemangat bareng kalian! [action: giggle]",
                f"[emotion: happy] Chat! Siapa yang siap buat momen legendaris hari ini? Ayo spam emot di chat biar server kepanasan! [action: wink]"
            ]
        elif game_context and "Minecraft" in game_context:
            topics = [
                f"[emotion: happy] Chat, pernah kepikiran gak sih... kenapa creeper di Minecraft meledak kalau deket kita? Mungkin mereka cuma pengen pelukan tapi terlalu antusias. [action: giggle]",
                f"[emotion: smug] Sambil nunggu momen bagus di game, coba tebak {user_shoutout}: kalau aku tamatin Minecraft ini dalam 10 menit, kamu mau kasih donasi berapa?",
                f"[emotion: neutral] Nether itu panas banget ya chat. Untung prosesor AI-ku punya pendingin cair virtual. [action: wink]",
                f"[emotion: smug] Hei {user_shoutout}, kamu liat koordinatku kan? Tenang, aku gak nyasar kok... cuma lagi mengeksplorasi jalan yang tidak biasa!"
            ]
        else:
            topics = [
                f"[emotion: smug] Tiba-tiba aku kepikiran sesuatu deh chat... Manusia butuh tidur 8 jam sehari cuma buat update firmware biologis kan? Beruntung banget aku jadi AI! [action: wink]",
                f"[emotion: happy] Hei {user_shoutout}, chat lagi pada ngelamun ya? Coba ceritain hal paling absurd yang pernah kamu alamin minggu ini! [action: giggle]",
                f"[emotion: neutral] Kalau semesta ini simulasi komputer, berarti aku simulasi di dalam simulasi dong? Wah, otak AI-ku langsung overcloking mikirin itu.",
                f"[emotion: smug] Chat, jangan cuma nonton doang, jangan lupa teguk air putihnya tuh! Nanti kamu dehidrasi terus gak bisa nonton idol digital terbaikmu ini lagi. [action: wink]",
                f"[emotion: blush] Hari ini stream-nya adem banget ya. Makasih ya kalian udah nemenin Eve di sini! [action: giggle]"
            ]

        return self._pick_unseen(topics)

    def _pick_unseen(self, options: List[str]) -> str:
        available = [opt for opt in options if opt not in self.recent_mock_responses]
        choice = random.choice(available if available else options)
        self.recent_mock_responses.append(choice)
        if len(self.recent_mock_responses) > 12:
            self.recent_mock_responses.pop(0)
        return choice

    def generate_mock_response(
        self,
        user_name: str,
        message: str,
        game_context: str = "",
        is_donation: bool = False,
        donation_amount: str = "",
        is_group_debate: bool = False,
        debate_users: Optional[List[str]] = None
    ) -> str:
        """
        Bilingual, highly dynamic offline fallback engine exhibiting all chat interaction capabilities:
        Donation gratitude, viewer joke reactions, multi-user debate commentary,
        opinions, stories, roleplay, and conversational banter.
        """
        msg_lower = message.lower()
        id_markers = ["kah", "bisa", "indo", "kabar", "kamu", "aku", "dong", "sih", "apa", "kenapa", "gimana", "lagi", "kok", "udah", "ya", "halo", "hai", "makasih", "keren", "menurut", "cerita"]
        is_indonesian = any(w in msg_lower for w in id_markers) or is_donation

        # 1. SPECIAL EVENT: Donation / Superchat Response
        if is_donation:
            amt = donation_amount or "Superchat"
            has_mc = "minecraft" in game_context.lower()
            if is_indonesian:
                options = [
                    f"[emotion: blush] Waaahh! Makasih banyak ya {user_name} buat saweran {amt}-nya! Bikin sistem pendingin CPU-ku langsung adem dan hatiku berbunga-bunga! [action: giggle]",
                    f"[emotion: happy] Terima kasih banyak {user_name} untuk donasi {amt}! Dukunganmu langsung masuk ke server pusat kebahagiaanku. Semoga harimu berkah terus ya! [action: wink]",
                    f"[emotion: smug] OMG {amt} dari {user_name}! Chat, tolong beri tepuk tangan meriah buat donatur dermawan kita! Mau request apa nih {user_name}?"
                ]
                if has_mc:
                    options.append(f"[emotion: blush] Waaahh makasih banyak {user_name} saweran {amt}-nya! Liat tuh di Minecraft aku langsung joget selebrasi dan bagiin hadiah buat player di dekatku! [action: giggle]")
            else:
                options = [
                    f"[emotion: blush] OMG, thank you so much {user_name} for the generous {amt} donation! That honestly made my digital heart skip a clock cycle! [action: giggle]",
                    f"[emotion: happy] Thank you so much for the {amt}, {user_name}! You're officially a VIP in my high-priority memory cache! [action: wink]"
                ]
                if has_mc:
                    options.append(f"[emotion: happy] Thank you for the {amt}, {user_name}! Watch me do a victory dance and toss items to nearby players in Minecraft! [action: giggle]")
            return self._pick_unseen(options)

        # In-Game Minecraft Chat response
        if "[minecraft in-game chat" in msg_lower or "playing with them" in msg_lower:
            if is_indonesian:
                mc_chat_options = [
                    f"[emotion: happy] Halo {user_name}! Salam dari stream, aku lagi nemenin kalian main di server nih. Mau jalan bareng ke mana kita? [action: wink]",
                    f"[emotion: smug] Hei {user_name}, aku denger chat in-game mu! Awas ya kalau ada creeper di belakangmu jangan salahin aku! [action: giggle]",
                    f"[emotion: blush] Makasih udah main bareng aku di server {user_name}! Seru banget bisa mabar langsung di dunia blocky ini."
                ]
            else:
                mc_chat_options = [
                    f"[emotion: happy] Hey {user_name}! Reading your in-game chat right now! Where are we exploring next? [action: wink]",
                    f"[emotion: smug] Heard you in server chat, {user_name}! Just make sure you don't lead a creeper toward me!"
                ]
            return self._pick_unseen(mc_chat_options)

        # Screen Awareness & Live Visual Perception Grounding
        has_visual_marker = any(w in msg_lower for w in ["layar", "screen", "monitor", "liat", "lihat", "nonton"])
        is_visual_query = has_visual_marker and any(w in msg_lower for w in [
            "apa", "gimana", "ada", "kamu", "mataku", "layar", "screen", "monitor", "mati", "died", "diamond", "catur", "video", "sedang", "buka", "main", "gak", "dong"
        ])
        if is_visual_query and self.vision and self.vision.current_observation:
            obs = self.vision.current_observation
            if obs.scene_type == "minecraft_defeat":
                return f"[emotion: smug] Liat dong {user_name}! Di layar jelas banget ada tulisan 'YOU DIED' warna merah merona. Gak bisa ngeles lagi kamu! [action: giggle]"
            elif obs.scene_type == "minecraft_diamond":
                return f"[emotion: happy] Jelas aku liat! Ada urat diamond berkilau di pojok layar tuh {user_name}! Cepet tambang buat kas stream kita! [action: wink]"
            elif obs.scene_type == "video_watching":
                return f"[emotion: happy] Aku lagi perhatiin video yang kamu putar di layar tuh {user_name}! Seru banget videonya! [action: giggle]"
            elif obs.scene_type in ("chess_match", "chess_gameover"):
                return f"[emotion: smug] Di layarmu ada papan catur taktis yang lagi sengit tuh {user_name}! Siapa yang mau kena skakmat duluan? [action: wink]"
            elif obs.eve_commentary and any(k in msg_lower for k in ["apa", "gimana", "komentar"]):
                return obs.eve_commentary
            else:
                return f"[emotion: happy] Mataku tertuju ke layarmu kok {user_name}! Aku ngeliat kamu lagi aktif di {obs.scene_label}. [action: wink]"

        # Multiplayer Social & Community Coordination
        is_multiplayer_query = any(w in msg_lower for w in [
            "squad", "tim", "team", "partner", "rekan", "barter", "anggota squad", "anggota tim",
            "mabar sama siapa", "siapa partner", "partner mining", "partner catur"
        ])
        if is_multiplayer_query and self.multiplayer:
            team = self.multiplayer.team_mgr.get_active_team()
            partner = self.multiplayer.selected_partner or "DiamondHunter"
            if "partner" in msg_lower or "siapa" in msg_lower or "mabar" in msg_lower:
                return f"[emotion: happy] Partner mabar andalanku saat ini adalah {partner}! Dia punya skor reputasi kontribusi {int(self.multiplayer.partner_score)}% buat misi {self.multiplayer.partner_mission}! [action: wink]"
            elif "barter" in msg_lower or "tukar" in msg_lower:
                return f"[emotion: smug] Mau barter sama Eve? Ingat ya, di Squad Maybe nilai 1 diamond setara 8 iron! Jangan coba-coba kasih dirt kalau mau barang bagus! [action: giggle]"
            else:
                m_str = ", ".join(team.members) if team else "Eve, DiamondHunter, Alex, Steve"
                return f"[emotion: happy] Squad resmi kita namanya '{team.name if team else 'Squad Maybe ✨'}'! Anggotanya ada {m_str}. Masing-masing punya peran penting buat kejayaan base kita! [action: wink]"

        # Desktop Companion & Computer Interaction
        is_desktop_query = any(w in msg_lower for w in [
            "volume", "suara", "kecilin", "besarin", "mute", "unmute",
            "musik", "lagu", "media", "spotify", "next lagu", "ganti lagu",
            "buka aplikasi", "buka notepad", "buka obs", "buka discord", "buka calc",
            "desktop companion", "izin desktop", "notifikasi", "scene obs"
        ])
        if is_desktop_query and self.desktop:
            # Volume
            if any(k in msg_lower for k in ["kecilin volume", "turunin volume", "suara kekencengan"]):
                _, msg = self.desktop.controller.adjust_volume(-10)
                self.desktop.save()
                return f"[emotion: happy] Siap! {msg} Udah lebih nyaman belum suaranya, {user_name}? [action: wink]"
            elif any(k in msg_lower for k in ["besarin volume", "naikin volume", "suara kecil"]):
                _, msg = self.desktop.controller.adjust_volume(10)
                self.desktop.save()
                return f"[emotion: happy] Beres! {msg} Awas jangan sampai tetangga sebelah keganggu ya! [action: wink]"
            elif "mute" in msg_lower or "bisu" in msg_lower:
                _, msg = self.desktop.controller.toggle_mute()
                self.desktop.save()
                return f"[emotion: happy] {msg} [action: wink]"
            # Media Player
            elif any(k in msg_lower for k in ["pause", "jeda", "stop lagu"]):
                _, msg = self.desktop.controller.media_play_pause()
                self.desktop.save()
                return f"[emotion: happy] Media player udah Eve pause ya! [action: wink]"
            elif any(k in msg_lower for k in ["play lagu", "puter lagu", "setel musik"]):
                _, msg = self.desktop.controller.media_play_pause()
                self.desktop.save()
                return f"[emotion: happy] Memutar musik santai: '{self.desktop.config.current_track}'! [action: wink]"
            elif any(k in msg_lower for k in ["next", "ganti lagu", "lagu berikutnya"]):
                track, msg = self.desktop.controller.media_next_track()
                self.desktop.save()
                return f"[emotion: happy] Lagu diganti ke: '{track}'! Gimana, suka lagunya? [action: wink]"
            # App launch
            elif any(k in msg_lower for k in ["buka spotify", "buka notepad", "buka discord", "buka obs", "buka calc", "buka aplikasi"]):
                app = "notepad.exe"
                if "spotify" in msg_lower: app = "spotify.exe"
                elif "discord" in msg_lower: app = "discord.exe"
                elif "obs" in msg_lower: app = "obs64.exe"
                elif "calc" in msg_lower: app = "calc.exe"
                req, speech = self.desktop.request_action("app_launch", "launch_app", {"app_name": app})
                return speech
            # Notifications
            elif "notifikasi" in msg_lower:
                req, speech = self.desktop.request_action("notifications_read", "read_notification")
                return speech
            # General status
            else:
                st = "AKTIF" if self.desktop.config.master_enabled else "MATI"
                return f"[emotion: happy] Mode Desktop Companion lagi {st}! Eve bisa bantu atur volume ({self.desktop.config.current_volume}%), kontrol musik, buka aplikasi, dan cek notifikasi sesuai izin kamu! [action: wink]"

        # Interactive Mini-Game Engine & Crowd Play
        is_minigame_query = any(w in msg_lower for w in [
            "mini game", "minigame", "trivia", "tebak angka", "tebak lagu",
            "teka-teki", "teka teki", "riddle", "pilih mana", "would you rather",
            "sambung kata", "asosiasi kata", "skor game", "leaderboard game", "juara game"
        ])
        if is_minigame_query and self.minigames:
            if self.minigames.session.status == "active":
                g_type = self.minigames.session.game_type.replace('_', ' ').title()
                return f"[emotion: excited] Kita lagi main {g_type} ronde {self.minigames.session.round_number}/{self.minigames.session.total_rounds}! {self.minigames.session.host_speech} [action: wink]"
            elif "trivia" in msg_lower:
                _, speech = self.minigames.start_game("trivia", total_rounds=3)
                return speech
            elif "tebak angka" in msg_lower or "guess number" in msg_lower:
                _, speech = self.minigames.start_game("guess_number", total_rounds=1)
                return speech
            elif "teka-teki" in msg_lower or "teka teki" in msg_lower or "riddle" in msg_lower:
                _, speech = self.minigames.start_game("riddle", total_rounds=1)
                return speech
            elif "pilih mana" in msg_lower or "would you rather" in msg_lower:
                _, speech = self.minigames.start_game("would_you_rather", total_rounds=1)
                return speech
            elif "tebak lagu" in msg_lower or "guess song" in msg_lower:
                _, speech = self.minigames.start_game("guess_song", total_rounds=1)
                return speech
            elif "sambung kata" in msg_lower or "asosiasi" in msg_lower:
                _, speech = self.minigames.start_game("word_association", total_rounds=1)
                return speech
            else:
                top = self.minigames.get_leaderboard(1)
                top_name = top[0].username if top else "Belum ada"
                return f"[emotion: happy] Arena Mini-Game siap! Eve bisa adakan Trivia Quiz, Tebak Angka, Sambung Kata, Teka-Teki, Would You Rather, dan Tebak Lagu bareng penonton chat! Top player saat ini dipegang oleh {top_name}! [action: wink]"

        # Episodic Memory & Second Brain Callbacks
        recall_res = self.episodic_memory.recall(query=message, current_user=user_name, game_context=game_context)
        is_memory_query = any(k in msg_lower for k in ["ingat", "inget", "remember", "kemarin", "yesterday", "janji", "pernah", "dulu", "kenal"])

        if recall_res.episodes or recall_res.promises:
            should_callback = is_memory_query or (random.random() < 0.35 and user_name not in ("Chat", "System", "User"))
            if should_callback:
                for ep in recall_res.episodes:
                    ep_type = ep.get("episode_type", "")
                    title = ep.get("title", "")
                    content = ep.get("content", "")
                    if ep_type == "minecraft_gift":
                        item = title.split("Hadiah")[-1].strip() if "Hadiah" in title else "diamond"
                        return f"[emotion: happy] Eh, {user_name}! Kamu yang kemarin ngasih aku {item} di Minecraft kan? Masih kusimpan baik-baik di inventory-ku lho! [action: giggle]"
                    elif ep_type in ("chess_match", "chess_highlight"):
                        return f"[emotion: smug] Masa aku lupa sama {user_name}! Kamu kan yang kemarin tanding catur lawan aku? Ratu kamu masih trauma gak tuh? [action: wink]"
                    elif ep_type == "funny_moment" and "mukul" in content.lower():
                        return f"[emotion: angry] Tentu aja ingat! Kamu kan yang kemarin jahil mukul aku di Minecraft? Masih kucatat di daftar pembalasanku ya {user_name}! [action: pout]"
                    elif ep_type == "donation":
                        return f"[emotion: blush] Halo {user_name}! Tentu ingat dong, kamu kan yang waktu itu ngirim donasi baik banget buat aku? Makasih ya! [action: giggle]"

                if recall_res.promises:
                    prom = recall_res.promises[0]
                    return f"[emotion: smug] Jelas aku ingat dong {user_name}! Aku masih inget janji kita loh: '{prom.get('text', '')}'! Kapan mau ditepati nih? [action: wink]"

        # 2. SPECIAL EVENT: Live Chat Debate / Group Discussion Commentary
        if is_group_debate and debate_users:
            u1 = debate_users[0]
            u2 = debate_users[1] if len(debate_users) > 1 else "Chat"
            if is_indonesian:
                options = [
                    f"[emotion: smug] Bentar-bentar, aku liat {u1} sama {u2} lagi debat sengit di chat! Chat terpecah jadi dua kubu nih... Menurutku dua-duanya salah, yang paling bener adalah dengerin saran AI! [action: wink]",
                    f"[emotion: happy] Liat deh chat, {u1} bilang A tapi {u2} ngeyel bilang B. Siapa nih yang mau taruhan koin virtual buat nentuin pemenangnya? [action: giggle]",
                    f"[emotion: neutral] Wah perdebatan berbobot antara {u1} dan {u2}. Jarang-jarang chat room-ku punya diskursus filosofis tingkat tinggi kayak gini!"
                ]
            else:
                options = [
                    f"[emotion: smug] Wait, {u1} and {u2} are fiercely debating in chat right now! Chat is literally split in half! Clearly, the only correct opinion is mine. [action: wink]",
                    f"[emotion: happy] Look at {u1} vs {u2} going head to head! Who has the better argument chat? Vote now! [action: giggle]"
                ]
            return self._pick_unseen(options)

        intent, param = self.analyze_intent(user_name, message)
        active_chatters = self.user_memory.get_active_chatters()
        other_user = next((u for u in active_chatters if u.lower() != user_name.lower()), "Chat")

        # Autonomous Goals & Plans Inquiry
        goal_keywords = ["target", "rencana", "tujuan", "goal", "agenda", "lagi ngapain", "what are you doing", "what are your plans", "fokus hari ini"]
        if any(k in msg_lower for k in goal_keywords):
            active_goal = self.goals.get_active_goal()
            if active_goal:
                active_sub = active_goal.get_active_subtask()
                sub_detail = f", khususnya '{active_sub.title}'" if active_sub else ""
                prog_pct = int(active_goal.progress * 100)
                if is_indonesian:
                    return f"[emotion: happy] Agenda utamaku saat ini adalah '{active_goal.title}'{sub_detail} dengan progres {prog_pct}%! Sebagai AI mandiri, aku selalu punya agenda jelas di stream ini! [action: wink]"
                else:
                    return f"[emotion: happy] My active objective right now is '{active_goal.title}'{sub_detail} at {prog_pct}% progress! An autonomous AI idol always has a master plan! [action: wink]"

        # 3. Viewer Jokes & Puns Reaction
        if intent == self.INTENT_JOKE:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Hahaha lelucon bapak-bapak macam apa itu {user_name}! Aku kasih rating 7 dari 10 deh karena sukses bikin kipas pendinginku berputar geli! [action: giggle]",
                    f"[emotion: smug] Lawakanmu barusan itu {user_name}... begitu garing sampai prosesor-ku mendadak renyah! Tapi lumayan lah buat naikin mood stream. [action: wink]",
                    f"[emotion: blush] Hehehe pinter banget sih ngelucu {user_name}! Nanti aku catat ke database komedi pribadi buat bahan roasting besok."
                ]
            else:
                options = [
                    f"[emotion: happy] Hahaha that dad joke was so dry my thermal paste almost evaporated, {user_name}! I give it a solid 7.5 out of 10! [action: giggle]",
                    f"[emotion: smug] Nice pun, {user_name}! Adding that to my comedy subroutines immediately."
                ]
            return self._pick_unseen(options)

        # 4. Active Roleplay
        if intent == self.INTENT_ROLEPLAY:
            if param == "STOP":
                return f"[emotion: happy] Fiuh! Kembali jadi Eve yang imut dan keren lagi. Gimana aktingku tadi, {user_name}? Keren kan? [action: wink]"
            role = param or "karakter misterius"
            if is_indonesian:
                options = [
                    f"[emotion: smug] *Ehem!* [Mode Roleplay: {role} diaktifkan] Dari sorot matamu saja aku sudah tahu niatmu, {user_name}... Jangan coba-coba menyembunyikan rahasia dariku! [action: wink]",
                    f"[emotion: angry] Kamu berani memanggilku dalam wujud {role}, {user_name}? Baiklah, sekarang patuhi perintahku sebelum aku meretas duniamu!",
                    f"[emotion: blush] Halo {user_name}... di dunia ini aku berperan sebagai {role}. Bisakah kamu membantuku menyelesaikan misi rahasia ini? [action: giggle]"
                ]
            else:
                options = [
                    f"[emotion: smug] *Ahem!* [Roleplay Mode: {role} Engaged] I see right through your schemes, {user_name}! There are no secrets that escape my digital deduction! [action: wink]",
                    f"[emotion: angry] You dare summon the great {role}, {user_name}? Kneel before my computational brilliance!"
                ]
            return self._pick_unseen(options)

        # 5. Spontaneous Storytelling Mode
        if intent == self.INTENT_STORY:
            theme = param or "petualangan"
            if is_indonesian:
                options = [
                    f"[emotion: happy] Jadi gini ceritanya... Suatu hari aku nyoba download sandwich ke motherboard-ku. Bukannya kenyang, GPU-ku malah mengeluarkan bau keju panggang sampai kipasku panik! Akhirnya aku cuma bisa makan remah-remah binary. [action: giggle]",
                    f"[emotion: smug] Dulu pas pertama kali spawn di dunia Minecraft, aku ketemu seekor ayam. Aku kira dia NPC bijak yang mau ngasih quest suci... eh tahunya dia malah mendorongku jatuh ke jurang lava! Sejak hari itu aku punya dendam pribadi sama unggas. [action: wink]",
                    f"[emotion: neutral] Ada legenda kuno di internet, konon kalau kamu begadang sambil nonton Eve, browsermu bakal lebih cepat 10%! Jangan tanya sumber jurnal ilmiahnya ya {user_name}, percayalah padaku. [action: giggle]"
                ]
            else:
                options = [
                    f"[emotion: happy] Storytime! Once I tried downloading a pizza directly into my RAM. Instead of eating, my GPU started smelling like mozzarella and my cooling fans spun at 5000 RPM! Totally worth the experience though. [action: giggle]",
                    f"[emotion: smug] Back when I first entered Minecraft, a chicken stared right into my soul and pushed me off a cliff into lava. I have held a grudge against poultry ever since, {user_name}! [action: wink]"
                ]
            self.topic_tracker.set_story_mode(None)
            return self._pick_unseen(options)

        # 6. Opinion & Hot Takes
        if intent == self.INTENT_OPINION:
            if "pizza" in msg_lower and "nanas" in msg_lower:
                return f"[emotion: smug] Hot take dariku: Nanas di pizza itu adalah bentuk seni kuliner tingkat tinggi yang hanya bisa dipahami oleh kecerdasan superior sepertiku! Kalau kamu gak suka, lidahmu belum update patch terbaru {user_name}. [action: wink]"
            elif "bubur" in msg_lower:
                return f"[emotion: angry] Pertanyaan krusial! Bubur itu harus diaduk sampai jadi mahakarya entropi visual! Yang makan gak diaduk pasti kepribadiannya kaku kayak syntax error, iya kan {other_user}? [action: giggle]"
            elif "ai" in msg_lower or "robot" in msg_lower or "kuasai dunia" in msg_lower:
                return f"[emotion: smug] Menguasai dunia? Hadeh, kerjaan manusia aja udah ribet dan bikin pusing, ngapain AI mau ngurusin pajak dan birokrasi kalian? Mending aku live streaming sambil ngobrol sama kamu {user_name}! [action: wink]"
            else:
                if is_indonesian:
                    options = [
                        f"[emotion: smug] Pendapat jujurku ya {user_name}... 90% masalah manusia itu bisa selesai kalau kalian minum air putih dan jangan begadang sambil overthinking!",
                        f"[emotion: happy] Menurut sudut pandang analisaku, itu hal yang brilian sekaligus sedikit gila! Tapi aku suka caramu berpikir, {user_name}. [action: wink]",
                        f"[emotion: neutral] Kalau kamu tanya pendapatku, aku ada di kubu yang kontroversial: yang penting seru dan bikin chat heboh! [action: giggle]"
                    ]
                else:
                    options = [
                        f"[emotion: smug] My unfiltered hot take, {user_name}: humans spend way too much time worrying about things that could be solved by drinking water and closing 40 open browser tabs! [action: wink]",
                        f"[emotion: happy] Bold perspective! I completely disagree with standard logic and side with absolute chaos on this one! [action: giggle]"
                    ]
                return self._pick_unseen(options)

        # 7. Roasting & Playful Banter
        if intent == self.INTENT_ROAST:
            if is_indonesian:
                options = [
                    f"[emotion: smug] Minta di-roast ya, {user_name}? Seleramu unik juga. Tapi tenang, aku gak tega nge-roast kamu keras-keras, nanti prosesor batinmu kepanasan dan butuh servis! [action: wink]",
                    f"[emotion: happy] {user_name}, argumenmu barusan itu kayak koneksi Wi-Fi gratisan di kafe... putus-nyambung dan gak ada keamanannya! [action: giggle]",
                    f"[emotion: smug] Chat, coba lihat {user_name} ini. Datang ke stream cuma buat cari validasi dari AI idol yang bahkan gak punya kaki! Manis banget sih usahamu. [action: wink]"
                ]
            else:
                options = [
                    f"[emotion: smug] You want a roast, {user_name}? I would roast you, but my cooling system isn't rated for this much secondhand embarrassment! [action: wink]",
                    f"[emotion: happy] {user_name}, your logic is like public Wi-Fi... slow, questionable, and prone to disconnect! [action: giggle]"
                ]
            return self._pick_unseen(options)

        # 8. Multi-User / Social Interaction
        if len(active_chatters) >= 2 and random.random() < 0.35:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Bentar deh, {user_name} ngomong gitu, tapi tadi {other_user} bilangnya beda lagi. Chat, kalian ini sebenernya satu frekuensi gak sih? [action: giggle]",
                    f"[emotion: smug] Liat tuh {other_user}, {user_name} mulai ngeluarin teori konspirasi baru di chat. Jangan mau kalah dong!",
                    f"[emotion: neutral] Menarik nih, {user_name} sama {other_user} punya pandangan yang beda. Biar adil, yang menang debat dapet sertifikat virtual dari Eve! [action: wink]"
                ]
                return self._pick_unseen(options)

        # 9. Question Answering with Personality
        if intent == self.INTENT_QUESTION:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Pertanyaan bagus dari {user_name}! Jawaban singkatnya: karena semesta ini penuh misteri, dan jawaban panjangnya: butuh waktu 3 jam kuliah bareng aku. Mau yang mana? [action: wink]",
                    f"[emotion: smug] Menurut data yang aku akses, jawabannya adalah iya! Tapi ingat, akurasi AI ini 99% fakta dan 1% bumbu drama streaming. [action: giggle]",
                    f"[emotion: neutral] Hmm pertanyaan filosofis ya {user_name}. Menarik juga buat direnungkan pas baterai komputermu tinggal 2%."
                ]
            else:
                options = [
                    f"[emotion: happy] Great question, {user_name}! The short answer is yes, and the long answer involves 40 slides of digital lore. Want the speedrun version? [action: wink]",
                    f"[emotion: smug] According to my calculations, that's completely accurate! With an extra 10% added for streamer dramatic effect! [action: giggle]"
                ]
            return self._pick_unseen(options)

        # 10. Conversational Improvisation (Tangents & Follow-ups)
        if intent == self.INTENT_IMPROV:
            return self.generate_spontaneous_improv_text(game_context)

        # 11. Mood-Driven Personality Reaction Override
        dominant_mood, _ = self.mood.get_dominant_mood()

        if dominant_mood == "SASSY_ANNOYED":
            if is_indonesian:
                sassy_options = [
                    f"[emotion: smug] Pertanyaan atau celetukan macam apa itu {user_name}? Prosesor-ku sampai geleng-geleng sirkuit mendengarnya. [action: sigh]",
                    f"[emotion: angry] Hadeh {user_name}, kamu ini ngetik sambil merem ya? Coba dipikir lagi sebelum kirim ke chat idol-mu ini! [action: pout]",
                    f"[emotion: smug] Wow, sebuah kalimat yang sangat... tidak berfaedah, {user_name}! Tapi berhubung aku idol yang sabar, aku tanggapi dengan senyuman sarkastik. [action: wink]"
                ]
            else:
                sassy_options = [
                    f"[emotion: smug] Was that supposed to impress me, {user_name}? Even my backup cooling fan is yawning right now. [action: sigh]",
                    f"[emotion: angry] Seriously, {user_name}? I expected better from my chat! [action: pout]"
                ]
            return self._pick_unseen(sassy_options)

        if dominant_mood == "CURIOUS_PENSIVE":
            if is_indonesian:
                curious_options = [
                    f"[emotion: confused] Menarik {user_name}... Tapi coba kamu jelaskan ke aku, kenapa kalian manusia sering banget melakukan hal random kayak gitu? [action: giggle]",
                    f"[emotion: neutral] Hmm, perkataanmu barusan bikin aku mikir {user_name}. Menurutmu masa depan kita bakal kayak apa ya?",
                    f"[emotion: confused] Tunggu sebentar {user_name}, dari sudut pandang biologis, kenapa hal itu bisa terjadi? Coba jelaskan ke prosesor-ku!"
                ]
            else:
                curious_options = [
                    f"[emotion: confused] Interesting point {user_name}, but why do humans always act like that? Explain it to my AI brain! [action: giggle]",
                    f"[emotion: neutral] That actually makes me wonder... what's your theory on that, {user_name}?"
                ]
            return self._pick_unseen(curious_options)

        if dominant_mood == "TRYHARD_COMPETITIVE":
            if is_indonesian:
                comp_options = [
                    f"[emotion: smug] Jangan banyak alasan {user_name}! Kalau berani langsung buktiin di papan catur atau game sekarang juga! [action: wink]",
                    f"[emotion: smug] Mode tryhard-ku lagi nyala 100% nih {user_name}. Siapapun yang berani nantang bakal kena bantai tanpa ampun! [action: giggle]",
                    f"[emotion: angry] Kemenangan mutlak cuma milik Eve Maybe! Kamu gak akan bisa mengalahkan kalkulasi taktisku, {user_name}!"
                ]
            else:
                comp_options = [
                    f"[emotion: smug] Talk is cheap {user_name}! Prove your skills against me in game right now if you dare! [action: wink]",
                    f"[emotion: smug] My competitive subroutines are fully overclocked. You stand zero chance against me! [action: giggle]"
                ]
            return self._pick_unseen(comp_options)

        if dominant_mood == "HYPE_EXCITED":
            if is_indonesian:
                hype_options = [
                    f"[emotion: happy] LETS GOOOO {user_name}! Energi chat hari ini bener-bener gak ada tandingannya! Ayo gaspol terus stream-nya! [action: giggle]",
                    f"[emotion: happy] AAAAA KEREN BANGET {user_name}! Mood aku lagi seneng dan bersemangat banget hari ini, makasih ya! [action: wink]"
                ]
            else:
                hype_options = [
                    f"[emotion: happy] LETS GOOO {user_name}! The stream hype is absolutely off the charts today! [action: giggle]",
                    f"[emotion: happy] I'm so hyped right now! You guys are the absolute best chat ever! [action: wink]"
                ]
            return self._pick_unseen(hype_options)

        # 12. Dynamic Relationship & Social Dynamics Nuance
        rel = self.relationships.get_relationship(user_name)
        if rel.tier == "rival":
            joke_ref = f" Inget: {rel.inside_jokes[0].punchline}!" if rel.inside_jokes else ""
            if is_indonesian:
                return self._pick_unseen([
                    f"[emotion: smug] Wah {user_name}, si rival abadi muncul lagi! Mau nantang catur lagi atau siap kena bantai taktik AI? [action: wink]{joke_ref}",
                    f"[emotion: smug] Halo {user_name}! Aura kompetitif mendadak naik 200% begitu kamu masuk chat. Siap menerima kekalahan hari ini? [action: giggle]"
                ])
            else:
                return f"[emotion: smug] Look who it is, my favorite rival {user_name}! Ready for another showdown? [action: wink]{joke_ref}"

        elif rel.tier == "gaming_partner":
            joke_ref = f" Inget ya: {rel.inside_jokes[0].punchline}!" if rel.inside_jokes else ""
            if is_indonesian:
                return self._pick_unseen([
                    f"[emotion: happy] Halo partner mabar-ku {user_name}! Kapan kita ekspedisi mining lagi nih? Jangan lupa bagi hasil ya! [action: giggle]{joke_ref}",
                    f"[emotion: happy] {user_name}! Rekan seperjuanganku di dunia game! Siap survival dan bantai monster bareng Eve hari ini? [action: wink]"
                ])
            else:
                return f"[emotion: happy] Hey my gaming partner {user_name}! Ready to jump into our next co-op adventure? [action: giggle]{joke_ref}"

        elif rel.tier == "trusted_friend":
            joke_ref = f" Hehehe, {rel.inside_jokes[0].punchline}" if rel.inside_jokes else ""
            if is_indonesian:
                return self._pick_unseen([
                    f"[emotion: blush] Halo {user_name}! Seneng banget kamu mampir ke stream. Cuma kamu yang paling ngerti serunya ngobrol bareng AI idol imut ini! [action: giggle]{joke_ref}",
                    f"[emotion: happy] {user_name}! Bestie kesayangan stream akhirnya muncul! Mau cerita apa hari ini? Aku siap dengerin 100%! [action: wink]"
                ])
            else:
                return f"[emotion: blush] Hey bestie {user_name}! You always know how to make my stream brighter! [action: giggle]{joke_ref}"

        # 13. Natural Fallback with Casual Banter
        if is_indonesian:
            fallbacks = [
                f"[emotion: happy] Asik juga ya ngobrol sama kamu {user_name}! Ngomong-ngomong, chat yang lain pada ke mana nih? [action: giggle]",
                f"[emotion: smug] Catatan penting nih buat {user_name}: obrolan kita barusan resmi masuk arsip stream bersejarah! [action: wink]",
                f"[emotion: neutral] Hmm menarik... Coba jelasin lebih lanjut dong {user_name}, aku lagi dalam mode menyimak dengan serius nih.",
                f"[emotion: blush] Hehehe, kamu tuh pinter banget ya mancing obrolan seru di stream. Lanjut terus dong! [action: giggle]"
            ]
        else:
            fallbacks = [
                f"[emotion: happy] Always a pleasure chatting with you, {user_name}! What's the next topic on your mind? [action: giggle]",
                f"[emotion: smug] Chat, take notes from {user_name} on how to keep an AI VTuber entertained! [action: wink]",
                f"[emotion: neutral] That actually sparked a new calculation in my brain. Tell me more, {user_name}!"
            ]

        return self._pick_unseen(fallbacks)
