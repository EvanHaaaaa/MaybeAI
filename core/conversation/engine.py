import random
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from core.conversation.memory import UserMemory, ContextMemory, TopicTracker
from core.conversation.prompts import MasterPromptBuilder

class ConversationEngine:
    """
    Central orchestration engine for Eve Maybe's conversation abilities.
    Maintains user memories, conversational context, topic tracking,
    intent classification, prompt synthesis, and offline fallback generators.
    """

    INTENT_STORY = "story"
    INTENT_ROLEPLAY = "roleplay"
    INTENT_OPINION = "opinion"
    INTENT_QUESTION = "question"
    INTENT_ROAST = "roast"
    INTENT_IMPROV = "improv"
    INTENT_GENERAL = "general"

    def __init__(self, character: Dict[str, Any]):
        self.character = character
        self.user_memory = UserMemory()
        self.context_memory = ContextMemory(max_buffer_turns=16)
        self.topic_tracker = TopicTracker()
        self.recent_mock_responses: List[str] = []
        self.last_interaction_time: float = time.time()

    def record_incoming(self, user: str, text: str):
        self.last_interaction_time = time.time()
        self.user_memory.record_message(user, text)
        self.topic_tracker.update_topic(text)

    def record_turn(self, user: str, user_text: str, bot_response: str):
        self.context_memory.add_turn("user", user, user_text)
        self.context_memory.add_turn("assistant", self.character.get("nickname", "Eve"), bot_response)

    def analyze_intent(self, user: str, text: str) -> Tuple[str, Optional[str]]:
        """
        Classifies conversational intent and extracts parameters (e.g. roleplay target, story theme).
        """
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

        # 6. Questions & Inquiries
        q_markers = ["apa", "kenapa", "mengapa", "gimana", "bagaimana", "siapa", "kapan", "dimana", "why", "how", "what", "who", "when", "where", "?"]
        if any(lower.startswith(m) for m in q_markers) or lower.endswith("?"):
            return self.INTENT_QUESTION, clean

        return self.INTENT_GENERAL, None

    def build_system_prompt(self, current_user: str, game_context: str = "") -> str:
        social_context = self.user_memory.get_social_context(current_user)
        return MasterPromptBuilder.build_system_prompt(
            character=self.character,
            active_topic=self.topic_tracker.current_topic,
            active_roleplay=self.topic_tracker.active_roleplay,
            active_story=self.topic_tracker.active_story,
            social_context=social_context,
            rolling_summary=self.context_memory.rolling_summary,
            game_context=game_context
        )

    def generate_spontaneous_improv_text(self, game_context: str = "") -> str:
        """
        Generates an autonomous stream thought, shower thought, or engaging chat prompt
        to prevent dead air during stream or gameplay.
        """
        active_chatters = self.user_memory.get_active_chatters()
        user_shoutout = random.choice(active_chatters) if active_chatters else "Chat"

        if game_context and "Minecraft" in game_context:
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

    def generate_mock_response(self, user_name: str, message: str, game_context: str = "") -> str:
        """
        Bilingual, highly dynamic offline fallback engine exhibiting all 10 capabilities:
        Natural conversation, context awareness, retention, humor, storytelling,
        opinions, roleplay, QA, improvisation, and multi-user interaction.
        """
        msg_lower = message.lower()
        id_markers = ["kah", "bisa", "indo", "kabar", "kamu", "aku", "dong", "sih", "apa", "kenapa", "gimana", "lagi", "kok", "udah", "ya", "halo", "hai", "makasih", "keren", "menurut", "cerita"]
        is_indonesian = any(w in msg_lower for w in id_markers)

        intent, param = self.analyze_intent(user_name, message)
        active_chatters = self.user_memory.get_active_chatters()
        other_user = next((u for u in active_chatters if u.lower() != user_name.lower()), "Chat")

        # 1. Active Roleplay or Roleplay Activation
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

        # 2. Spontaneous Storytelling Mode
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

        # 3. Opinion & Hot Takes
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

        # 4. Roasting & Playful Banter
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

        # 5. Multi-User / Social Interaction
        if len(active_chatters) >= 2 and random.random() < 0.35:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Bentar deh, {user_name} ngomong gitu, tapi tadi {other_user} bilangnya beda lagi. Chat, kalian ini sebenernya satu frekuensi gak sih? [action: giggle]",
                    f"[emotion: smug] Liat tuh {other_user}, {user_name} mulai ngeluarin teori konspirasi baru di chat. Jangan mau kalah dong!",
                    f"[emotion: neutral] Menarik nih, {user_name} sama {other_user} punya pandangan yang beda. Biar adil, yang menang debat dapet sertifikat virtual dari Eve! [action: wink]"
                ]
                return self._pick_unseen(options)

        # 6. Question Answering with Personality
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

        # 7. Conversational Improvisation (Tangents & Follow-ups)
        if intent == self.INTENT_IMPROV:
            return self.generate_spontaneous_improv_text(game_context)

        # 8. Natural Fallback with Casual Banter
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
