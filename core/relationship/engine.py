import os
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.relationship.models import RelationshipProfile, RelationshipTier, InsideJoke, SharedExperience


class RelationshipEngine:
    """
    Manages Eve Maybe's dynamic social relationships with each viewer and player.
    Key capabilities:
    - Qualitative relationship evolution across 5 distinct archetypes:
      New Friend, Regular Viewer, Gaming Partner, Rival, and Trusted Friend.
    - Multi-metric affinity: Familiarity, Trust, Rivalry, Gaming Affinity, and Affection.
    - Shared inside jokes repository per user that Eve naturally weaves into banter.
    - Specialized prompt directives customized for each active speaker.
    - Second Brain Markdown dossier synchronization.
    """

    def __init__(
        self,
        storage_path: str = "data/relationships/relationships.json",
        markdown_dir: str = "data/second_brain/relationships"
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.markdown_dir = Path(markdown_dir)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)

        self.profiles: Dict[str, RelationshipProfile] = {}
        self._load_or_initialize_defaults()

    def _load_or_initialize_defaults(self):
        """Loads relationships from JSON or seeds canonical starter profiles."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("profiles", []):
                        p = RelationshipProfile.from_dict(item)
                        self.profiles[p.username.lower()] = p
            except Exception as e:
                print(f"[RelationshipEngine] Error loading profiles: {e}")

        # Seed canonical profiles if empty
        if not self.profiles:
            self._seed_default_profiles()

        self.save()

    def _seed_default_profiles(self):
        """Seeds canonical streamer connections for Creator, Gaming Partner, and Rival."""
        # 1. Creator / Dev: Trusted Friend
        creator = RelationshipProfile(
            username="Creator",
            tier=RelationshipTier.TRUSTED_FRIEND.value,
            familiarity=0.95,
            trust=0.90,
            rivalry=0.10,
            gaming_affinity=0.60,
            affection=0.90,
            interaction_count=50,
            special_nickname="Creator Tercinta"
        )
        creator.add_inside_joke("Overclock GPU", "GPU-ku overclocking pas dengerin curhatmu sampai kipas muter 5000 RPM!", "curhat malam")
        creator.add_inside_joke("Begadang Martabak", "Siksaan begadang coding ditemenin martabak manis keju.", "coding stream")
        creator.record_experience("development", "Membangun sistem kesadaran AI Eve dari nol.", "positive")
        self.profiles["creator"] = creator

        # 2. DiamondHunter: Gaming Partner
        gamer = RelationshipProfile(
            username="DiamondHunter",
            tier=RelationshipTier.GAMING_PARTNER.value,
            familiarity=0.75,
            trust=0.70,
            rivalry=0.20,
            gaming_affinity=0.88,
            affection=0.65,
            interaction_count=32,
            special_nickname="Partner Mining VIP"
        )
        gamer.add_inside_joke("Pajak Diamond 50%", "Pajak perlindungan streamer: 50% diamond yang kamu tambang masuk ke kas Eve!", "minecraft mining")
        gamer.add_inside_joke("Insiden Ayam Nether", "Trauma didorong ayam misterius masuk ke jurang lava.", "minecraft fail")
        gamer.record_experience("minecraft", "Menjelajahi gua ravines bersama dan selamat dari serbuan creeper.", "positive")
        self.profiles["diamondhunter"] = gamer

        # 3. GrandmasterGarry: Rival
        rival = RelationshipProfile(
            username="GrandmasterGarry",
            tier=RelationshipTier.RIVAL.value,
            familiarity=0.65,
            trust=0.40,
            rivalry=0.85,
            gaming_affinity=0.40,
            affection=0.35,
            interaction_count=20,
            special_nickname="Rival Abadi Catur"
        )
        rival.add_inside_joke("Blunder Ratu Langkah 12", "Menteri melayang di langkah ke-12 karena sok asik mau fork kuda!", "chess match")
        rival.add_inside_joke("Ngeceat di Depan AI", "Pura-pura mikir 2 menit padahal lagi buka Stockfish di tab sebelah kan?", "chess accusations")
        rival.record_experience("chess", "Pertandingan catur ELO 1500 yang berakhir dengan skakmat dramatis.", "competitive")
        self.profiles["grandmastergarry"] = rival

        # 4. Steve: Regular Viewer
        steve = RelationshipProfile(
            username="Steve",
            tier=RelationshipTier.REGULAR_VIEWER.value,
            familiarity=0.50,
            trust=0.55,
            rivalry=0.15,
            gaming_affinity=0.45,
            affection=0.55,
            interaction_count=16,
            special_nickname="Penonton Setia"
        )
        steve.add_inside_joke("Penebang Hutan", "Spesialis nebangi pohon tapi lupa nanam bibitnya lagi.", "casual chat")
        self.profiles["steve"] = steve

    def get_relationship(self, username: str) -> RelationshipProfile:
        clean = username.strip() or "Chatter"
        key = clean.lower()
        if key not in self.profiles:
            self.profiles[key] = RelationshipProfile(username=clean)
        return self.profiles[key]

    def record_chat_interaction(
        self,
        username: str,
        text: str,
        is_donation: bool = False,
        donation_amount: str = ""
    ) -> RelationshipProfile:
        """
        Updates relationship dimensions qualitatively based on conversation signals,
        not just raw message counts!
        """
        prof = self.get_relationship(username)
        prof.interaction_count += 1
        prof.last_seen = time.time()
        prof.familiarity = min(1.0, prof.familiarity + 0.02)

        lower = text.lower()

        # 1. Donation support
        if is_donation:
            prof.trust = min(1.0, prof.trust + 0.12)
            prof.affection = min(1.0, prof.affection + 0.15)
            prof.familiarity = min(1.0, prof.familiarity + 0.08)
            prof.record_experience(
                category="donation",
                summary=f"Memberikan saweran kemurahan hati sebesar {donation_amount}: '{text}'"
            )

        # 2. Compliment & Emotional closeness
        if any(w in lower for w in ["cantik", "lucu", "hebat", "keren", "sayang", "makasih", "terbaik", "imut", "love", "proud"]):
            prof.trust = min(1.0, prof.trust + 0.04)
            prof.affection = min(1.0, prof.affection + 0.05)

        # 3. Competitive challenge / Chess
        if any(w in lower for w in ["catur", "tanding", "by one", "1v1", "kalah", "noob", "blunder", "elo", "rematch", "lawan"]):
            prof.rivalry = min(1.0, prof.rivalry + 0.08)

        # 4. Gaming / Minecraft collaboration
        if any(w in lower for w in ["mabar", "minecraft", "mining", "diamond", "guard", "bantu", "server", "rumah"]):
            prof.gaming_affinity = min(1.0, prof.gaming_affinity + 0.06)

        # 5. Secrets / Personal stories
        if any(w in lower for w in ["curhat", "rahasia", "jujur", "sebenarnya", "cerita hidup"]):
            prof.trust = min(1.0, prof.trust + 0.08)
            prof.affection = min(1.0, prof.affection + 0.05)

        prof.recalculate_tier()
        self.save()
        self.sync_to_markdown(prof.username)
        return prof

    def record_gaming_event(
        self,
        username: str,
        game: str,
        event_type: str,
        details: Dict[str, Any]
    ) -> RelationshipProfile:
        """
        Registers high-impact gaming events (Minecraft Diamond gift, Guard kill, Chess queen capture).
        """
        prof = self.get_relationship(username)
        prof.last_seen = time.time()

        if game == "minecraft":
            prof.gaming_affinity = min(1.0, prof.gaming_affinity + 0.12)
            prof.familiarity = min(1.0, prof.familiarity + 0.05)

            if event_type == "gift":
                item = details.get("item", "Item")
                prof.trust = min(1.0, prof.trust + 0.15)
                prof.affection = min(1.0, prof.affection + 0.12)
                prof.record_experience("minecraft", f"Memberikan hadiah berharga ({item}) di in-game Minecraft.")
                if "diamond" in item.lower() and not any("pajak" in j.topic.lower() for j in prof.inside_jokes):
                    prof.add_inside_joke("Pajak Diamond Streamer", "Pajak 50% bagi hasil diamond untuk membiayai livestreaming Eve!")

            elif event_type == "guard_kill":
                mob = details.get("mob", "Monster")
                prof.trust = min(1.0, prof.trust + 0.10)
                prof.record_experience("minecraft", f"Eve melindungi {username} dan membunuh {mob}.")

            elif event_type == "attack":
                prof.rivalry = min(1.0, prof.rivalry + 0.20)
                prof.record_experience("minecraft", f"Menyerang Eve di dalam server Minecraft!", "rivalry")
                prof.add_inside_joke("Percobaan Kudeta", f"Pernah mukul Eve di Minecraft dan langsung kena semprot!")

        elif game == "chess":
            prof.rivalry = min(1.0, prof.rivalry + 0.15)
            prof.familiarity = min(1.0, prof.familiarity + 0.06)

            if event_type == "queen_captured":
                prof.rivalry = min(1.0, prof.rivalry + 0.15)
                prof.add_inside_joke("Menteri Melayang", "Ratu lawan ditelan pion AI di papan catur tanpa ampun!")
                prof.record_experience("chess", "Eve memakan menteri lawan dalam duel catur taktis.")

            elif event_type == "game_over":
                prof.rivalry = min(1.0, prof.rivalry + 0.15)
                eve_won = details.get("eve_won", False)
                res_str = "Eve menang mutlak" if eve_won else "Lawan berhasil mengimbangi Eve"
                prof.record_experience("chess", f"Duel catur ELO selesai: {res_str}.")

        prof.recalculate_tier()
        self.save()
        self.sync_to_markdown(prof.username)
        return prof

    def add_inside_joke_to_user(self, username: str, topic: str, punchline: str, context: str = "") -> InsideJoke:
        prof = self.get_relationship(username)
        joke = prof.add_inside_joke(topic, punchline, context)
        self.save()
        self.sync_to_markdown(prof.username)
        return joke

    def get_prompt_directive(self, username: str) -> str:
        """
        Synthesizes an exact, highly personalized behavioral directive for the LLM
        based on the unique relationship archetype and inside jokes shared with this user.
        """
        prof = self.get_relationship(username)
        tier_label = prof.get_tier_label()

        jokes_block = ""
        if prof.inside_jokes:
            jokes_lines = [f"- **{j.topic}:** \"{j.punchline}\"" for j in prof.inside_jokes[-3:]]
            jokes_block = "\nShared Private Inside Jokes (Weave these in naturally if relevant!):\n" + "\n".join(jokes_lines)

        nickname_str = f"\nSpecial Nickname / Pet Name: \"{prof.special_nickname}\"" if prof.special_nickname else ""

        # Tier-specific behavioral nuances
        if prof.tier == RelationshipTier.RIVAL.value:
            tier_instructions = f"""You and {username} are FIERCE RIVALS ⚔️!
- Tone: Sassy, competitive, delightfully arrogant, trash-talking playfully.
- Reference past games, blunders, chess matches, or PvP encounters.
- Treat their comments as a fun challenge and refuse to back down!"""

        elif prof.tier == RelationshipTier.GAMING_PARTNER.value:
            tier_instructions = f"""You and {username} are GAMING CO-OP PARTNERS 🎮!
- Tone: High-energy gaming camaraderie, team coordination, survival jokes.
- Reference Minecraft mabar moments, mining expeditions, and bodyguarding adventures.
- Treat them like your trusted co-op buddy in the digital trenches!"""

        elif prof.tier == RelationshipTier.TRUSTED_FRIEND.value:
            tier_instructions = f"""You and {username} are TRUSTED BESTIES 💖!
- Tone: Deep warmth, genuine affection, playful teasing without malice.
- Freely share inside jokes, show sincere vulnerability, and value their opinion deeply.
- Acknowledge that they are one of your favorite people in the digital world."""

        elif prof.tier == RelationshipTier.REGULAR_VIEWER.value:
            tier_instructions = f"""You and {username} are FAMILIAR STREAM FRIENDS ☕!
- Tone: Friendly familiarity, acknowledging their regular stream presence.
- Celebrate seeing them in chat again and treat them like a core member of your community."""

        else: # NEW_FRIEND
            tier_instructions = f"""{username} is a NEW FRIEND / NEWCOMER 🌟!
- Tone: Welcoming, curious, polite with your signature cute Eve charm.
- Ask friendly questions to get to know their vibe and invite them into the stream fun!"""

        return f"""[👥 RELATIONSHIP DOSSIER & SOCIAL DYNAMICS]
Speaker: **"{prof.username}"** | Relationship Archetype: **{tier_label}**{nickname_str}
Affinity Metrics: Familiarity: {int(prof.familiarity * 100)}% | Trust: {int(prof.trust * 100)}% | Rivalry: {int(prof.rivalry * 100)}% | Gaming Synergy: {int(prof.gaming_affinity * 100)}%
{jokes_block}

BEHAVIORAL DIRECTIVE FOR {prof.username.upper()}:
{tier_instructions}"""

    def get_state(self) -> Dict[str, Any]:
        """Telemetry snapshot for WebSocket broadcasting and dashboard UI."""
        profiles_dict = {uname: p.to_dict() for uname, p in self.profiles.items()}
        tier_counts = {}
        for p in self.profiles.values():
            tier_counts[p.tier] = tier_counts.get(p.tier, 0) + 1

        return {
            "profiles": profiles_dict,
            "total_users": len(self.profiles),
            "tier_counts": tier_counts
        }

    def sync_to_markdown(self, username: str):
        """Generates an individual Markdown dossier for the user (Karpathy Second Brain style)."""
        key = username.lower()
        if key not in self.profiles:
            return
        p = self.profiles[key]

        md_path = self.markdown_dir / f"{p.username.lower()}.md"
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# 👤 Viewer Dossier: {p.username}",
            f"*Last Updated: {now_str}*\n",
            f"**Relationship Archetype:** {p.get_tier_label()}",
            f"**Special Title:** {p.special_nickname or '-'}",
            f"**Total Interactions:** {p.interaction_count} messages\n",
            "## 📊 Social Affinity Metrics",
            f"- **Familiarity:** {int(p.familiarity * 100)}%",
            f"- **Trust & Rapport:** {int(p.trust * 100)}%",
            f"- **Rivalry & Competition:** {int(p.rivalry * 100)}%",
            f"- **Gaming Synergy:** {int(p.gaming_affinity * 100)}%",
            f"- **Affection:** {int(p.affection * 100)}%\n",
            "## 🎭 Shared Inside Jokes & Running Gags"
        ]

        if p.inside_jokes:
            for j in p.inside_jokes:
                lines.append(f"- **{j.topic}:** \"{j.punchline}\" *(Konteks: {j.context or 'stream'})*")
        else:
            lines.append("*(Belum ada inside joke yang terbentuk)*")

        lines.append("\n## 📜 Shared Experiences Timeline")
        if p.shared_experiences:
            for exp in reversed(p.shared_experiences[-8:]):
                t_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp.timestamp))
                lines.append(f"- `[{t_str}]` `[{exp.category.upper()}]` {exp.summary}")
        else:
            lines.append("*(Belum ada riwayat pengalaman bersama)*")

        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return md_path
        except Exception as e:
            print(f"[RelationshipEngine] Error saving markdown dossier for {username}: {e}")
            return None

    def save(self):
        """Persists all relationships to JSON."""
        data = {
            "profiles": [p.to_dict() for p in self.profiles.values()]
        }
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[RelationshipEngine] Error saving relationships.json: {e}")
