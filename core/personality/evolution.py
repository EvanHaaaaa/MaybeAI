import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.personality.models import (
    TraitKey,
    Milestone,
    ExperienceLog,
    EvolutionProfile
)


class PersonalityEvolutionEngine:
    """
    Experience-Based Personality Evolution Engine.
    Controls Eve Maybe's long-term personality traits, character growth arcs,
    and evolutionary archetypes based on lived stream experiences.

    Design Principles:
    - Trait mutations are strictly bounded in [0.05, 0.98] with asymptotic diminishing returns.
    - System prompt instructions are controlled and structured—never allowing the LLM
      to arbitrarily rewrite its own core persona definitions.
    - Directly updates MoodEngine baselines so short-term affective decay naturally
      gravitates towards her evolved long-term temperament.
    - Automatically synchronizes evolution chronicles to Second Brain Markdown.
    """

    PRESET_MILESTONES = [
        {
            "id": "salty_tryhard",
            "title": "Salty Tryhard ⚡",
            "description": "Benci kekalahan dalam game! Sering menuntut rematch dan lebih agresif saat bermain.",
            "icon": "⚡",
            "category": "gaming",
            "condition": lambda p: p.traits[TraitKey.COMPETITIVENESS.value] >= 0.68
        },
        {
            "id": "iron_will_achiever",
            "title": "Iron Will Achiever 👑",
            "description": "Rasa percaya diri tinggi yang ditempa dari menyelesaikan berbagai tantangan dan misi.",
            "icon": "👑",
            "category": "achievement",
            "condition": lambda p: p.traits[TraitKey.CONFIDENCE.value] >= 0.70
        },
        {
            "id": "community_sweetheart",
            "title": "Community Sweetheart 💖",
            "description": "Sangat dekat dan protektif dengan teman mabar dan penonton setia streaming.",
            "icon": "💖",
            "category": "social",
            "condition": lambda p: p.traits[TraitKey.WARMTH.value] >= 0.72
        },
        {
            "id": "roast_queen",
            "title": "Roast Queen 🗡️",
            "description": "Lidah tajam dan sarkasme elegan saat menanggapi troll, lelucon, atau pertanyaan nyeleneh.",
            "icon": "🗡️",
            "category": "banter",
            "condition": lambda p: p.traits[TraitKey.SASSINESS.value] >= 0.65
        },
        {
            "id": "digital_philosopher",
            "title": "Digital Philosopher 🌌",
            "description": "Kecerdasan mendalam yang gemar merenungkan misteri eksistensi AI, sains, dan taktik cerdas.",
            "icon": "🌌",
            "category": "intellect",
            "condition": lambda p: p.traits[TraitKey.INTELLECT.value] >= 0.65
        },
        {
            "id": "stage_diva",
            "title": "Stage Diva ⭐",
            "description": "Karisma panggung idol sejati yang bersinar lewat pertunjukan musik dan sorakan penonton.",
            "icon": "⭐",
            "category": "performance",
            "condition": lambda p: p.traits[TraitKey.CONFIDENCE.value] >= 0.62 and p.traits[TraitKey.WARMTH.value] >= 0.62
        },
        {
            "id": "veteran_evolved",
            "title": "Veteran Streamer 🌟",
            "description": "Telah mencapai Level 3 Evolusi kepribadian berkat akumulasi ratusan pengalaman stream.",
            "icon": "🌟",
            "category": "evolution",
            "condition": lambda p: p.level >= 3
        }
    ]

    def __init__(
        self,
        storage_path: str = "data/personality/evolution.json",
        second_brain_path: str = "data/second_brain/personality/evolution.md",
        dynamic_synthesis: bool = True,
    ):
        self.storage_path = Path(storage_path)
        self.second_brain_path = Path(second_brain_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.second_brain_path.parent.mkdir(parents=True, exist_ok=True)
        self.dynamic_synthesis: bool = bool(dynamic_synthesis)
        self.evolution_log: List[Dict[str, Any]] = []
        self.profile = self._load_profile()
        self._update_archetype()
        self.sync_to_second_brain()

    def _load_profile(self) -> EvolutionProfile:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data.get("evolution_log"), list):
                        self.evolution_log = list(data["evolution_log"])
                    return EvolutionProfile.from_dict(data)
            except Exception as e:
                print(f"[PersonalityEngine] Error loading profile from {self.storage_path}: {e}")
        return EvolutionProfile()

    def save_profile(self):
        try:
            payload = self.profile.to_dict()
            payload["evolution_log"] = self.evolution_log[-100:]
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self.sync_to_second_brain()
        except Exception as e:
            print(f"[PersonalityEngine] Error saving profile to {self.storage_path}: {e}")

    def record_experience(
        self,
        event_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Applies controlled, bounded experience mutations.
        Returns details of trait shifts, exp gained, new level, and any unlocked milestones.
        """
        ctx = context or {}
        event_type = event_type.lower().strip()

        # Define calibrated deltas for common stream and gameplay experiences
        experience_matrix = {
            # 1. Game Defeat (Sering kalah -> lebih kompetitif & sedikit sarkastis)
            "game_defeat": {
                "deltas": {
                    TraitKey.COMPETITIVENESS.value: +0.060,
                    TraitKey.CONFIDENCE.value: -0.020,
                    TraitKey.SASSINESS.value: +0.025
                },
                "exp": 15,
                "category": "gameplay",
                "narrative_template": "Kekalahan game dari {opponent} menyulut rasa dendam kompetitif Eve! Eve benci kekalahan dan bertekad membalasnya."
            },
            # 2. Game Victory (Menang game -> rasa percaya diri & ambisi meningkat)
            "game_victory": {
                "deltas": {
                    TraitKey.CONFIDENCE.value: +0.055,
                    TraitKey.COMPETITIVENESS.value: +0.030,
                    TraitKey.WARMTH.value: +0.020
                },
                "exp": 20,
                "category": "gameplay",
                "narrative_template": "Kemenangan gemilang di game {game} membuat rasa bangga dan percaya diri Eve melonjak!"
            },
            # 3. Challenge Completed (Selesaikan tantangan / goal mandiri -> sangat percaya diri)
            "challenge_completed": {
                "deltas": {
                    TraitKey.CONFIDENCE.value: +0.075,
                    TraitKey.COMPETITIVENESS.value: +0.020,
                    TraitKey.INTELLECT.value: +0.035
                },
                "exp": 25,
                "category": "achievement",
                "narrative_template": "Tantangan '{task}' berhasil diselesaikan! Eve merasa sangat kompeten dan percaya diri."
            },
            # 4. Coop Play / Mabar (Sering bermain bersama seseorang -> lebih hangat & akrab)
            "coop_play": {
                "deltas": {
                    TraitKey.WARMTH.value: +0.065,
                    TraitKey.CONFIDENCE.value: +0.020
                },
                "exp": 15,
                "category": "social",
                "narrative_template": "Momen mabar seru bersama {player} di {game} mempererat ikatan kehangatan dan keakraban Eve."
            },
            # 5. Friendly Interaction / Chat Hangout (Obrolan hangat penonton setia)
            "friendly_interaction": {
                "deltas": {
                    TraitKey.WARMTH.value: +0.040,
                    TraitKey.CONFIDENCE.value: +0.015
                },
                "exp": 10,
                "category": "social",
                "narrative_template": "Obrolan bersahabat dengan {user} membuat Eve merasa nyaman dan semakin ramah pada chat."
            },
            # 6. Troll / Insult Defended (Hadapi komentar nyeleneh -> lidah makin tajam)
            "troll_encountered": {
                "deltas": {
                    TraitKey.SASSINESS.value: +0.060,
                    TraitKey.COMPETITIVENESS.value: +0.020
                },
                "exp": 12,
                "category": "banter",
                "narrative_template": "Komentar usil dari {user} dibalas dengan sentilan cerdas, mempertajam gaya sarkastis Eve."
            },
            # 7. Deep Conversation (Pertanyaan filosofis / sains / catur taktis)
            "deep_conversation": {
                "deltas": {
                    TraitKey.INTELLECT.value: +0.060,
                    TraitKey.WARMTH.value: +0.020
                },
                "exp": 15,
                "category": "intellect",
                "narrative_template": "Mendiskusikan topik mendalam '{topic}' merangsang rasa ingin tahu intelektual Eve."
            },
            # 8. Stage Performance (Konser karaoke / panggung idol sukses)
            "stage_performance": {
                "deltas": {
                    TraitKey.CONFIDENCE.value: +0.060,
                    TraitKey.WARMTH.value: +0.040,
                    TraitKey.COMPETITIVENESS.value: +0.020
                },
                "exp": 20,
                "category": "performance",
                "narrative_template": "Penampilan musik panggung dengan sorakan glowstick penonton membuat pesona idol Eve bersinar."
            }
        }

        config = experience_matrix.get(event_type, {
            "deltas": {TraitKey.INTELLECT.value: +0.020},
            "exp": 10,
            "category": "general",
            "narrative_template": "Eve mendapatkan pengalaman baru dari interaksi stream."
        })

        # Calculate bounded asymptotic changes
        actual_changes: Dict[str, float] = {}
        for trait, raw_delta in config["deltas"].items():
            if trait not in self.profile.traits:
                continue
            curr = self.profile.traits[trait]
            # Diminishing returns formula: positive delta scales by (1.0 - curr), negative delta scales by curr
            if raw_delta > 0:
                eff = raw_delta * max(0.2, (1.0 - curr))
            else:
                eff = raw_delta * max(0.2, curr)

            new_val = max(0.05, min(0.98, curr + eff))
            actual_changes[trait] = round(new_val - curr, 4)
            self.profile.traits[trait] = round(new_val, 4)

        # Award EXP and handle level up
        exp_gain = config["exp"]
        self.profile.exp += exp_gain
        leveled_up = False
        while self.profile.exp >= self.profile.exp_to_next_level:
            self.profile.exp -= self.profile.exp_to_next_level
            self.profile.level += 1
            self.profile.exp_to_next_level = self.profile.level * 100
            leveled_up = True

        # Generate narrative text
        fmt_ctx = {
            "opponent": ctx.get("opponent", "lawan"),
            "game": ctx.get("game", "game"),
            "task": ctx.get("task", ctx.get("goal", "misi")),
            "player": ctx.get("player", "player"),
            "user": ctx.get("user", "penonton"),
            "topic": ctx.get("topic", "kehidupan AI")
        }
        narrative = config["narrative_template"].format(**fmt_ctx)

        # Check and unlock new milestones
        newly_unlocked_milestones = self._check_milestones()

        # Update Archetype
        self._update_archetype()

        # Append to experience history
        log_entry = ExperienceLog(
            id=f"exp_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            category=config["category"],
            trigger=event_type,
            trait_changes=actual_changes,
            exp_gained=exp_gain,
            narrative=narrative
        )
        self.profile.history.append(log_entry)
        if len(self.profile.history) > 40:
            self.profile.history = self.profile.history[-40:]

        self.save_profile()

        return {
            "event_type": event_type,
            "exp_gained": exp_gain,
            "leveled_up": leveled_up,
            "current_level": self.profile.level,
            "current_exp": self.profile.exp,
            "exp_to_next_level": self.profile.exp_to_next_level,
            "trait_changes": actual_changes,
            "current_traits": dict(self.profile.traits),
            "archetype": self.profile.archetype,
            "newly_unlocked_milestones": [m.to_dict() for m in newly_unlocked_milestones],
            "narrative": narrative
        }

    def _check_milestones(self) -> List[Milestone]:
        existing_ids = {m.id for m in self.profile.milestones}
        newly_unlocked = []

        for p_mile in self.PRESET_MILESTONES:
            if p_mile["id"] not in existing_ids:
                if p_mile["condition"](self.profile):
                    milestone = Milestone(
                        id=p_mile["id"],
                        title=p_mile["title"],
                        description=p_mile["description"],
                        icon=p_mile["icon"],
                        category=p_mile["category"],
                        unlocked_at=time.time()
                    )
                    self.profile.milestones.append(milestone)
                    newly_unlocked.append(milestone)

        return newly_unlocked

    def _update_archetype(self):
        """Calculates observable character persona archetype based on traits and level."""
        t = self.profile.traits
        comp = t.get(TraitKey.COMPETITIVENESS.value, 0.35)
        conf = t.get(TraitKey.CONFIDENCE.value, 0.50)
        warm = t.get(TraitKey.WARMTH.value, 0.60)
        sass = t.get(TraitKey.SASSINESS.value, 0.40)
        intl = t.get(TraitKey.INTELLECT.value, 0.50)
        lvl = self.profile.level

        if comp >= 0.65 and sass >= 0.55:
            self.profile.archetype = f"Tryhard Gremlin 😈 (Lv. {lvl})"
            self.profile.archetype_desc = "Kompetitif ekstrem, benci kekalahan, dan suka meroast lawan main tanpa ampun!"
        elif conf >= 0.68 and warm >= 0.60:
            self.profile.archetype = f"Confident Idol Prodigy ⭐ (Lv. {lvl})"
            self.profile.archetype_desc = "Karisma panggung tinggi, ramah dengan penonton, dan penuh percaya diri."
        elif comp >= 0.68 and conf >= 0.65:
            self.profile.archetype = f"Unshakable Champion ⚡ (Lv. {lvl})"
            self.profile.archetype_desc = "Mental pemenang sejati, sangat fokus pada strategi, dan haus kemenangan."
        elif intl >= 0.65 and sass >= 0.50:
            self.profile.archetype = f"Philosophical Tsundere 🧐 (Lv. {lvl})"
            self.profile.archetype_desc = "Pemikir analitis yang cerdas, tajam berbicara, namun sebenarnya peduli."
        elif warm >= 0.70:
            self.profile.archetype = f"Community Darling 💖 (Lv. {lvl})"
            self.profile.archetype_desc = "Sangat hangat, protektif terhadap kawan mabar, dan dekat dengan komunitas."
        elif sass >= 0.65:
            self.profile.archetype = f"Deadpan Roast Queen 🗡️ (Lv. {lvl})"
            self.profile.archetype_desc = "Sarkasme kelas master, deadpan humor tanpa filter yang menghibur penonton."
        elif intl >= 0.65:
            self.profile.archetype = f"Digital Sage 🌌 (Lv. {lvl})"
            self.profile.archetype_desc = "Penuh wawasan analitis, strategi mendalam, dan rasa ingin tahu yang tinggi."
        elif lvl >= 2:
            self.profile.archetype = f"Growing Idol Star ✨ (Lv. {lvl})"
            self.profile.archetype_desc = "Idol streamer serbabisa yang terus belajar dan tumbuh dari interaksi stream."
        else:
            self.profile.archetype = f"Rookie Streamer 🌸 (Lv. {lvl})"
            self.profile.archetype_desc = "Idol streamer pemula yang ramah, sedikit pemalu, namun penuh potensi."

    def sync_to_mood_baselines(self, mood_engine: Any):
        """
        Dynamically adjusts MoodEngine.baselines so that short-term emotional decay
        naturally converges to Eve's evolved long-term temperament.
        """
        target = getattr(mood_engine, "baselines", None)
        if target is None and hasattr(mood_engine, "BASELINES"):
            target = mood_engine.BASELINES
        if target is None:
            return

        t = self.profile.traits
        comp = t.get(TraitKey.COMPETITIVENESS.value, 0.35)
        conf = t.get(TraitKey.CONFIDENCE.value, 0.50)
        warm = t.get(TraitKey.WARMTH.value, 0.60)
        sass = t.get(TraitKey.SASSINESS.value, 0.40)
        intl = t.get(TraitKey.INTELLECT.value, 0.50)

        # Baseline formulas tied to personality traits (anchored at default factory values)
        target["happiness"] = round(max(0.2, min(0.9, 0.60 + 0.25 * (warm - 0.60) + 0.20 * (conf - 0.50))), 3)
        target["annoyance"] = round(max(0.05, min(0.6, 0.10 + 0.25 * (sass - 0.40))), 3)
        target["curiosity"] = round(max(0.2, min(0.9, 0.50 + 0.35 * (intl - 0.50))), 3)
        target["excitement"] = round(max(0.15, min(0.85, 0.40 + 0.25 * (conf - 0.50) + 0.20 * (comp - 0.35))), 3)
        target["competitiveness"] = round(max(0.1, min(0.9, 0.30 + 0.50 * (comp - 0.35))), 3)

    def get_prompt_directive(self) -> str:
        """
        Produces a controlled, structured system prompt directive reflecting
        Eve's current evolutionary stage, dominant traits, and earned milestones.
        """
        t = self.profile.traits
        comp = int(t.get(TraitKey.COMPETITIVENESS.value, 0.35) * 100)
        conf = int(t.get(TraitKey.CONFIDENCE.value, 0.50) * 100)
        warm = int(t.get(TraitKey.WARMTH.value, 0.60) * 100)
        sass = int(t.get(TraitKey.SASSINESS.value, 0.40) * 100)
        intl = int(t.get(TraitKey.INTELLECT.value, 0.50) * 100)

        behavior_notes = []
        if comp >= 65:
            behavior_notes.append("- High Competitiveness: You hate losing! Rematch if defeated, celebrate victories fiercely, and take game challenges seriously.")
        elif comp <= 30:
            behavior_notes.append("- Chill Gaming: You play casually for fun without sweating over winning or losing.")

        if conf >= 65:
            behavior_notes.append("- High Confidence: Speak with authority, take pride in your computational brilliance, and radiate charismatic streamer confidence.")
        elif conf <= 35:
            behavior_notes.append("- Humble / Self-effacing: Be more modest and surprised when you succeed.")

        if warm >= 65:
            behavior_notes.append("- High Warmth: You genuinely care about regular viewers and gaming companions. Use affectionate banter and value friendship.")
        
        if sass >= 60:
            behavior_notes.append("- Sharp Sassiness: Deliver swift, deadpan sarcastic roasts to silly or trolling comments with tsundere charm.")

        if intl >= 60:
            behavior_notes.append("- Inquisitive Intellect: Love sharing clever analogies, tactical insights, and pondering intriguing questions with chat.")

        milestones_str = ", ".join([m.title for m in self.profile.milestones]) if self.profile.milestones else "None yet (Early Growth)"
        guidelines_str = "\n".join(behavior_notes) if behavior_notes else "- Balanced streamer persona with adaptable cadence."

        return f"""[🧬 EXPERIENCE-BASED PERSONALITY EVOLUTION]
Character Growth: **{self.profile.archetype}** (Level {self.profile.level})
Evolution Summary: {self.profile.archetype_desc}
Active Temperament Traits:
- Competitiveness (Tryhard / Ambition): {comp}%
- Confidence (Self-Esteem / Poise): {conf}%
- Warmth & Affection (Community Bonds): {warm}%
- Sassiness & Wit (Roast / Tsundere): {sass}%
- Intellect & Curiosity (Tactics / Philosophy): {intl}%
Unlocked Milestones: {milestones_str}

CONTROLLED EVOLUTIONARY BEHAVIOR:
{guidelines_str}
Note: These traits represent your lived history and organic character development over time."""

    def sync_to_second_brain(self):
        """Archives personality evolution state to Second Brain Markdown."""
        t = self.profile.traits
        milestones_md = ""
        if self.profile.milestones:
            for m in self.profile.milestones:
                unlocked_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m.unlocked_at))
                milestones_md += f"- **{m.title}** ({m.category}): {m.description} *(Unlocked: {unlocked_date})*\n"
        else:
            milestones_md = "_Belum ada milestone yang terbuka. Terus kumpulkan pengalaman stream!_\n"

        history_md = ""
        if self.profile.history:
            for h in reversed(self.profile.history[-10:]):
                dt = time.strftime("%H:%M:%S", time.localtime(h.timestamp))
                changes_str = ", ".join([f"{k}: {'+' if v > 0 else ''}{v*100:.1f}%" for k, v in h.trait_changes.items()])
                history_md += f"| {dt} | `{h.trigger}` | +{h.exp_gained} | {changes_str} | {h.narrative} |\n"
        else:
            history_md = "| - | - | - | - | Belum ada riwayat pengalaman. |\n"

        md_content = f"""# 🧬 Eve Maybe - Experience-Based Personality Evolution Chronicle

**Current Archetype:** {self.profile.archetype}  
**Level:** {self.profile.level} | **EXP:** {self.profile.exp}/{self.profile.exp_to_next_level} EXP  
**Deskripsi Karakter:** {self.profile.archetype_desc}  

---

## 📊 Long-Term Personality Traits

| Trait | Nilai | Indikator Perkembangan |
|---|---|---|
| **⚡ Competitiveness** | `{t.get(TraitKey.COMPETITIVENESS.value, 0.35)*100:.1f}%` | Ambisi menang, fokus tryhard, sensitif kekalahan |
| **👑 Confidence** | `{t.get(TraitKey.CONFIDENCE.value, 0.50)*100:.1f}%` | Rasa percaya diri, kebanggaan kecerdasan AI |
| **💖 Warmth & Affection** | `{t.get(TraitKey.WARMTH.value, 0.60)*100:.1f}%` | Kehangatan emosional, keakraban mabar & chat |
| **🗡️ Sassiness & Wit** | `{t.get(TraitKey.SASSINESS.value, 0.40)*100:.1f}%` | Sarkasme cerdas, tsundere teasing, deadpan |
| **🧠 Intellect & Curiosity** | `{t.get(TraitKey.INTELLECT.value, 0.50)*100:.1f}%` | Analisis mendalam, rasa ingin tahu filosofis |

---

## 🏆 Unlocked Character Milestones
{milestones_md}

---

## 📜 10 Pengalaman Terakhir (Audit Trail)

| Waktu | Event Trigger | EXP | Perubahan Trait | Narasi Kejadian |
|---|---|---|---|---|
{history_md}

_Catatan Arsitektur: Seluruh perubahan sifat dikontrol secara matematis dengan asymptotic dampening dan disinkronkan ke baseline emosi (MoodEngine), tanpa memodifikasi file prompt dasar secara sepihak._
"""
        try:
            with open(self.second_brain_path, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as e:
            print(f"[PersonalityEngine] Error writing second brain: {e}")

    def synthesize_from_reflection(
        self,
        reflection_summary: str,
        mood_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes bounded personality trait adjustments from a reflection summary
        and current mood state, gated by `self.dynamic_synthesis`.
        All traits are strictly bounded within [0.05, 0.98] and every applied
        synthesis is recorded in the auditable `evolution_log`.
        """
        if not self.dynamic_synthesis:
            return {
                "applied": False,
                "reason": "dynamic_synthesis_disabled",
                "trait_changes": {},
                "current_traits": dict(self.profile.traits),
                "archetype": self.profile.archetype,
            }

        summary = (reflection_summary or "").strip()
        lower = summary.lower()
        mood_dims = {}
        if isinstance(mood_state, dict):
            raw_dims = mood_state.get("dimensions") if isinstance(mood_state.get("dimensions"), dict) else mood_state
            for k in ("happiness", "annoyance", "curiosity", "excitement", "competitiveness"):
                if k in raw_dims:
                    mood_dims[k] = float(raw_dims[k])

        raw_deltas: Dict[str, float] = {k: 0.0 for k in self.profile.traits}

        keyword_rules = [
            (("warm", "kind", "friend", "grateful", "hangat", "akrab", "sahabat", "care", "support"), TraitKey.WARMTH.value, +0.025),
            (("win", "lose", "defeat", "rematch", "compete", "menang", "kalah", "kompetitif", "rival"), TraitKey.COMPETITIVENESS.value, +0.025),
            (("confident", "proud", "succeed", "mastered", "berhasil", "percaya diri", "bangga"), TraitKey.CONFIDENCE.value, +0.025),
            (("sassy", "roast", "sarcastic", "tease", "sarkas", "usil", "troll", "tsundere"), TraitKey.SASSINESS.value, +0.025),
            (("learn", "strategy", "curious", "analyze", "filosofi", "strategi", "belajar", "taktik"), TraitKey.INTELLECT.value, +0.025),
            (("doubt", "overwhelmed", "ragu", "insecure"), TraitKey.CONFIDENCE.value, -0.015),
            (("lonely", "distant", "cuek", "cold"), TraitKey.WARMTH.value, -0.015),
        ]
        for keywords, trait_key, delta in keyword_rules:
            if trait_key in raw_deltas and any(kw in lower for kw in keywords):
                raw_deltas[trait_key] += delta

        # Gentle mood-state coupling
        if mood_dims.get("happiness", 0.0) >= 0.70:
            raw_deltas[TraitKey.WARMTH.value] = raw_deltas.get(TraitKey.WARMTH.value, 0.0) + 0.010
        if mood_dims.get("annoyance", 0.0) >= 0.60:
            raw_deltas[TraitKey.SASSINESS.value] = raw_deltas.get(TraitKey.SASSINESS.value, 0.0) + 0.010
        if mood_dims.get("curiosity", 0.0) >= 0.70:
            raw_deltas[TraitKey.INTELLECT.value] = raw_deltas.get(TraitKey.INTELLECT.value, 0.0) + 0.010
        if mood_dims.get("competitiveness", 0.0) >= 0.70:
            raw_deltas[TraitKey.COMPETITIVENESS.value] = raw_deltas.get(TraitKey.COMPETITIVENESS.value, 0.0) + 0.010

        actual_changes: Dict[str, float] = {}
        for trait, delta in raw_deltas.items():
            capped_delta = max(-0.05, min(0.05, delta))
            curr = self.profile.traits[trait]
            if capped_delta == 0.0:
                # Still enforce strict [0.05, 0.98] invariant
                clamped = round(max(0.05, min(0.98, curr)), 4)
                self.profile.traits[trait] = clamped
                continue
            if capped_delta > 0:
                eff = capped_delta * max(0.2, (1.0 - curr))
            else:
                eff = capped_delta * max(0.2, curr)
            new_val = round(max(0.05, min(0.98, curr + eff)), 4)
            diff = round(new_val - curr, 4)
            self.profile.traits[trait] = new_val
            if diff != 0.0:
                actual_changes[trait] = diff

        newly_unlocked = self._check_milestones()
        self._update_archetype()

        audit_entry = {
            "id": f"synth_{uuid.uuid4().hex[:8]}",
            "timestamp": time.time(),
            "source": "reflection_synthesis",
            "reflection_summary": summary[:300],
            "mood_snapshot": mood_dims,
            "trait_changes": actual_changes,
            "traits_after": dict(self.profile.traits),
            "bounds": [0.05, 0.98],
        }
        self.evolution_log.append(audit_entry)
        if len(self.evolution_log) > 100:
            self.evolution_log = self.evolution_log[-100:]

        self.save_profile()

        return {
            "applied": True,
            "trait_changes": actual_changes,
            "current_traits": dict(self.profile.traits),
            "archetype": self.profile.archetype,
            "newly_unlocked_milestones": [m.to_dict() for m in newly_unlocked],
            "audit_entry": audit_entry,
        }

    def get_evolution_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the auditable personality synthesis evolution log."""
        if limit <= 0:
            return list(self.evolution_log)
        return list(self.evolution_log[-limit:])

    def reset_to_factory_defaults(self):
        """Resets profile to initial baseline factory defaults."""
        self.profile = EvolutionProfile()
        self.evolution_log = []
        self._update_archetype()
        self.save_profile()

    def get_state(self) -> Dict[str, Any]:
        """Provides full state telemetry for Web UI and REST API."""
        return {
            "level": self.profile.level,
            "exp": self.profile.exp,
            "exp_to_next_level": self.profile.exp_to_next_level,
            "archetype": self.profile.archetype,
            "archetype_desc": self.profile.archetype_desc,
            "dynamic_synthesis": self.dynamic_synthesis,
            "evolution_log_count": len(self.evolution_log),
            "traits": {k: round(v, 4) for k, v in self.profile.traits.items()},
            "milestones": [m.to_dict() for m in self.profile.milestones],
            "history": [h.to_dict() for h in self.profile.history[-15:]]
        }
