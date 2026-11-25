import os
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from core.planning.models import Goal, Subtask, GoalTier, GoalCategory, GoalStatus
from core.planning.decomposer import GoalDecomposer
from core.planning.replanner import StrategyReplanner


class GoalEngine:
    """
    Autonomous Goal & Planning Engine for Eve Maybe.
    Enables:
    - Hierarchical planning: Weekly, Daily, Short-term, and Social goals.
    - Subtask decomposition & progress tracking.
    - Dynamic strategy adaptation and replanning upon failure.
    - Autonomous agenda selection: Eve chooses her own activities without waiting for orders.
    - Seamless synchronization to Markdown (`data/goals/agenda.md`) and JSON storage.
    """

    def __init__(self, storage_dir: str = "data/goals"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.goals_json_path = self.storage_dir / "goals.json"
        self.agenda_md_path = self.storage_dir / "agenda.md"

        self.goals: Dict[str, Goal] = {}
        self.active_goal_id: Optional[str] = None
        self.last_strategy_pivot: Optional[Dict[str, Any]] = None

        self._load_or_initialize_defaults()

    def _load_or_initialize_defaults(self):
        """Loads saved goals from disk, or seeds standard starter goals."""
        if self.goals_json_path.exists():
            try:
                with open(self.goals_json_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    for item in raw_data.get("goals", []):
                        g = Goal.from_dict(item)
                        self.goals[g.id] = g
                    self.active_goal_id = raw_data.get("active_goal_id")
            except Exception as e:
                print(f"[GoalEngine] Error loading goals: {e}")

        # If no goals exist, initialize with canonical goals requested by user
        if not self.goals:
            self._seed_default_goals()

        # Ensure we have an active goal
        if not self.active_goal_id or self.active_goal_id not in self.goals:
            self._select_default_active_goal()

        self.save()

    def _seed_default_goals(self):
        """Initializes canonical starter goals requested in specification."""
        # 1. Daily Goal: Membangun rumah di Minecraft
        g1 = self.create_goal(
            title="Membangun rumah di Minecraft",
            description="Membangun rumah kayu yang nyaman dan aman di Minecraft sebagai markas stream.",
            tier=GoalTier.DAILY.value,
            category=GoalCategory.MINECRAFT.value,
            priority=8,
            autonomous=True
        )

        # 2. Short-term Goal: Mengumpulkan 64 iron
        g2 = self.create_goal(
            title="Mengumpulkan 64 iron",
            description="Menambang dan melebur 64 bijih besi untuk persiapan armor dan peralatan tempur.",
            tier=GoalTier.SHORT_TERM.value,
            category=GoalCategory.MINECRAFT.value,
            priority=7,
            autonomous=True
        )

        # 3. Weekly Goal: Menyelesaikan tantangan speedrun
        g3 = self.create_goal(
            title="Menyelesaikan tantangan speedrun",
            description="Tantangan mingguan: Mengalahkan Ender Dragon secepat mungkin dengan taktik speedrun.",
            tier=GoalTier.WEEKLY.value,
            category=GoalCategory.MINECRAFT.value,
            priority=9,
            autonomous=True
        )

        # 4. Social Goal: Berinteraksi dengan player yang belum dikenal
        g4 = self.create_goal(
            title="Berinteraksi dengan player yang belum dikenal",
            description="Menyapa pemain/penonton baru, mengajak ngobrol ramah, dan menyimpan profil mereka ke memory.",
            tier=GoalTier.SOCIAL.value,
            category=GoalCategory.SOCIAL.value,
            priority=8,
            autonomous=True
        )

    def _select_default_active_goal(self):
        """Selects first available in-progress or pending goal."""
        for g in self.goals.values():
            if g.status in (GoalStatus.IN_PROGRESS.value, GoalStatus.PENDING.value):
                self.active_goal_id = g.id
                g.status = GoalStatus.IN_PROGRESS.value
                return

    def create_goal(
        self,
        title: str,
        description: str = "",
        tier: str = GoalTier.DAILY.value,
        category: str = GoalCategory.GENERAL.value,
        priority: int = 5,
        autonomous: bool = True
    ) -> Goal:
        """Creates and decomposes a goal into subtasks."""
        goal_id = f"goal_{tier[:3]}_{uuid.uuid4().hex[:6]}"
        subtasks = GoalDecomposer.decompose(
            goal_title=title,
            description=description,
            tier=tier,
            category=category
        )

        goal = Goal(
            id=goal_id,
            title=title.strip(),
            description=description.strip(),
            tier=tier,
            category=category,
            status=GoalStatus.PENDING.value,
            subtasks=subtasks,
            priority=priority,
            autonomous=autonomous
        )
        goal.recalculate_progress()
        self.goals[goal.id] = goal
        self.save()
        return goal

    def get_active_goal(self) -> Optional[Goal]:
        if self.active_goal_id and self.active_goal_id in self.goals:
            return self.goals[self.active_goal_id]
        return None

    def set_active_goal(self, goal_id: str) -> Optional[Goal]:
        if goal_id in self.goals:
            self.active_goal_id = goal_id
            g = self.goals[goal_id]
            if g.status == GoalStatus.PENDING.value:
                g.status = GoalStatus.IN_PROGRESS.value
                if g.subtasks and g.subtasks[0].status == GoalStatus.PENDING.value:
                    g.subtasks[0].status = GoalStatus.IN_PROGRESS.value
            self.save()
            return g
        return None

    def get_all_goals(self) -> List[Goal]:
        return list(self.goals.values())

    def get_goals_by_tier(self, tier: str) -> List[Goal]:
        return [g for g in self.goals.values() if g.tier == tier]

    def autonomous_select_next_activity(self, mood_dimensions: Optional[Dict[str, float]] = None) -> Tuple[Optional[Goal], str]:
        """
        Autonomous Agentic Agenda Selection:
        Eve selects her own activity based on pending goals, urgency, and internal mood!
        - If Competitive high -> picks Speedrun or Chess goal.
        - If Curiosity / Social high -> picks Social goal.
        - Otherwise picks highest priority daily/short-term goal.
        """
        pending_goals = [
            g for g in self.goals.values()
            if g.status in (GoalStatus.PENDING.value, GoalStatus.IN_PROGRESS.value)
        ]

        if not pending_goals:
            # Autonomously synthesize a new engaging goal!
            new_goal = self.create_goal(
                title="Eksplorasi Dunia Baru & Interaksi Chat",
                description="Menjelajahi tempat baru secara spontan sambil berinteraksi akrab dengan penonton stream.",
                tier=GoalTier.DAILY.value,
                category=GoalCategory.STREAM.value,
                priority=6,
                autonomous=True
            )
            pending_goals = [new_goal]

        mood = mood_dimensions or {}
        comp = mood.get("competitiveness", 0.3)
        curious = mood.get("curiosity", 0.5)
        excited = mood.get("excitement", 0.4)

        chosen: Goal = pending_goals[0]
        if comp >= 0.65:
            # Prefer speedrun or chess
            comp_candidates = [g for g in pending_goals if g.category in (GoalCategory.MINECRAFT.value, GoalCategory.CHESS.value) and "speedrun" in g.title.lower()]
            if not comp_candidates:
                comp_candidates = [g for g in pending_goals if g.category == GoalCategory.CHESS.value]
            if comp_candidates:
                chosen = max(comp_candidates, key=lambda g: g.priority)
        elif curious >= 0.65:
            # Prefer social goals
            social_candidates = [g for g in pending_goals if g.tier == GoalTier.SOCIAL.value or g.category == GoalCategory.SOCIAL.value]
            if social_candidates:
                chosen = max(social_candidates, key=lambda g: g.priority)
        elif excited >= 0.75:
            perf_candidates = [g for g in pending_goals if g.category == GoalCategory.PERFORMANCE.value]
            if perf_candidates:
                chosen = max(perf_candidates, key=lambda g: g.priority)
            else:
                chosen = max(pending_goals, key=lambda g: g.priority)
        else:
            chosen = max(pending_goals, key=lambda g: g.priority)

        self.set_active_goal(chosen.id)
        chosen.status = GoalStatus.IN_PROGRESS.value
        active_sub = chosen.get_active_subtask()
        if active_sub and active_sub.status == GoalStatus.PENDING.value:
            active_sub.status = GoalStatus.IN_PROGRESS.value

        speech = f"[emotion: happy] Chat! Aku sudah memutuskan agenda mandiri kita selanjutnya: '{chosen.title}'! Langkah sekarang: {active_sub.title if active_sub else 'Mulai'}! [action: wink]"
        self.save()
        return chosen, speech

    def advance_subtask_progress(self, subtask_id: str, delta: float = 1.0) -> Dict[str, Any]:
        """Advances a specific subtask's progress count, completing it if target reached."""
        target_goal = None
        target_subtask = None

        for g in self.goals.values():
            for s in g.subtasks:
                if s.id == subtask_id:
                    target_goal = g
                    target_subtask = s
                    break
            if target_subtask:
                break

        if not target_subtask or not target_goal:
            return {"success": False, "error": "Subtask not found"}

        just_completed = target_subtask.update_progress(delta)
        target_goal.recalculate_progress()

        # If subtask finished, start next pending subtask
        next_subtask = None
        if just_completed:
            for s in target_goal.subtasks:
                if s.status == GoalStatus.PENDING.value:
                    s.status = GoalStatus.IN_PROGRESS.value
                    next_subtask = s
                    break

        goal_completed = (target_goal.status == GoalStatus.COMPLETED.value)
        self.save()

        return {
            "success": True,
            "subtask_completed": just_completed,
            "goal_completed": goal_completed,
            "goal": target_goal.to_dict(),
            "subtask": target_subtask.to_dict(),
            "next_subtask": next_subtask.to_dict() if next_subtask else None
        }

    def complete_current_subtask(self) -> Dict[str, Any]:
        """Convenience method to immediately mark the active subtask completed."""
        active_goal = self.get_active_goal()
        if not active_goal:
            return {"success": False, "error": "No active goal"}

        active_sub = active_goal.get_active_subtask()
        if not active_sub:
            return {"success": False, "error": "No active subtask"}

        active_sub.mark_completed()
        active_goal.recalculate_progress()

        # Activate next pending subtask
        next_sub = None
        for s in active_goal.subtasks:
            if s.status == GoalStatus.PENDING.value:
                s.status = GoalStatus.IN_PROGRESS.value
                next_sub = s
                break

        goal_completed = (active_goal.status == GoalStatus.COMPLETED.value)
        self.save()

        return {
            "success": True,
            "subtask_completed": True,
            "goal_completed": goal_completed,
            "goal": active_goal.to_dict(),
            "completed_subtask": active_sub.to_dict(),
            "next_subtask": next_sub.to_dict() if next_sub else None
        }

    def fail_and_replan_active_subtask(self, failure_reason: str) -> Tuple[Optional[Subtask], str]:
        """Triggers dynamic strategy replanning for the current active subtask."""
        active_goal = self.get_active_goal()
        if not active_goal:
            return None, "Tidak ada goal aktif untuk diadaptasi."

        active_sub = active_goal.get_active_subtask()
        if not active_sub:
            return None, "Tidak ada subtask aktif yang gagal."

        new_sub, speech = StrategyReplanner.replan_subtask(
            goal=active_goal,
            failed_subtask=active_sub,
            failure_reason=failure_reason
        )

        self.last_strategy_pivot = {
            "timestamp": time.time(),
            "goal_id": active_goal.id,
            "failed_subtask": active_sub.title,
            "reason": failure_reason,
            "new_subtask": new_sub.title,
            "strategy": new_sub.strategy
        }

        self.save()
        return new_sub, speech

    def evaluate_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluates domain events (Minecraft, Chess, Performance, Social, Mission) and
        automatically credits progress to the relevant active subtask, keeping agenda.md synced.
        """
        data = data or {}
        active_goal = self.get_active_goal()
        if not active_goal:
            self.save()
            return {"advanced": False}

        active_sub = active_goal.get_active_subtask()
        if not active_sub:
            self.save()
            return {"advanced": False}

        advanced = False
        delta = 1.0
        goal_text = f"{active_goal.title} {active_sub.title}".lower()

        if event_type == "minecraft_item_collected":
            item = str(data.get("item", "")).lower()
            cnt = float(data.get("count", 1.0))
            if any(term and (term in active_sub.title.lower() or term in active_sub.unit.lower()) for term in [item, "logs", "wood", "iron", "diamond"]):
                delta = cnt
                advanced = True

        elif event_type == "minecraft_speedrun_advance":
            if active_goal.category == GoalCategory.MINECRAFT.value or "speedrun" in active_goal.title.lower():
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type == "minecraft_guard_victory":
            if "guard" in active_sub.title.lower() or "mob" in active_sub.title.lower():
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type == "player_greeted":
            if active_goal.tier == GoalTier.SOCIAL.value or active_goal.category == GoalCategory.SOCIAL.value or "player" in active_sub.title.lower() or "sapa" in active_sub.title.lower():
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type == "chess_game_won":
            if active_goal.category == GoalCategory.CHESS.value or "catur" in goal_text or "chess" in goal_text:
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type == "chess_game_started":
            if active_goal.category == GoalCategory.CHESS.value or active_sub.category == GoalCategory.CHESS.value or any(w in goal_text for w in ["catur", "chess", "opening"]):
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type == "chess_move_played":
            if active_goal.category == GoalCategory.CHESS.value or active_sub.category == GoalCategory.CHESS.value or any(w in goal_text for w in ["catur", "chess", "opening", "skakmat"]):
                delta = float(data.get("delta", 1.0))
                advanced = True

        elif event_type in ("performance_completed", "song_completed"):
            if (
                active_goal.category in (GoalCategory.PERFORMANCE.value, GoalCategory.STREAM.value)
                or active_sub.category == GoalCategory.PERFORMANCE.value
                or any(w in goal_text for w in ["konser", "karaoke", "nyanyi", "lagu", "setlist", "performance", "idol", "encore"])
            ):
                delta = float(data.get("delta", data.get("count", 1.0)))
                advanced = True

        elif event_type == "glowsticks_reached":
            if (
                active_goal.category in (GoalCategory.PERFORMANCE.value, GoalCategory.STREAM.value)
                or active_sub.category == GoalCategory.PERFORMANCE.value
                or "glowstick" in active_sub.title.lower()
                or "glowstick" in active_sub.unit.lower()
                or "sorakan" in active_sub.title.lower()
            ):
                delta = float(data.get("delta", data.get("count", data.get("glowsticks", 1.0))))
                advanced = True

        elif event_type == "mission_subtask_executed":
            target_goal_id = data.get("goal_id")
            target_sub_id = data.get("subtask_id")
            if (not target_goal_id or target_goal_id == active_goal.id) and (not target_sub_id or target_sub_id == active_sub.id):
                delta = float(data.get("delta", 1.0))
                advanced = True

        if advanced:
            res = self.advance_subtask_progress(active_sub.id, delta=delta)
            return {"advanced": True, "details": res}

        self.save()
        return {"advanced": False}

    def get_goal_directive(self) -> str:
        """
        Constructs real-time prompt instruction for LLM to stay fully aligned
        with active objectives, current subtask progress, and strategy.
        """
        active_goal = self.get_active_goal()
        if not active_goal:
            return ""

        active_sub = active_goal.get_active_subtask()
        sub_desc = f"'{active_sub.title}' ({int(active_sub.progress * 100)}% - {active_sub.current_count}/{active_sub.target_count} {active_sub.unit})" if active_sub else "Semua subtask selesai"
        strat = active_sub.strategy if active_sub else "Persiapan evaluasi akhir"

        weekly_goals = self.get_goals_by_tier(GoalTier.WEEKLY.value)
        weekly_str = weekly_goals[0].title if weekly_goals else "Menyelesaikan tantangan stream"

        social_goals = self.get_goals_by_tier(GoalTier.SOCIAL.value)
        social_str = social_goals[0].title if social_goals else "Membangun interaksi akrab dengan penonton baru"

        pivot_note = ""
        if self.last_strategy_pivot and (time.time() - self.last_strategy_pivot.get("timestamp", 0)) < 300:
            pivot_note = f"\n- Recent Tactical Pivot: {self.last_strategy_pivot.get('reason')} -> Plan B: {self.last_strategy_pivot.get('new_subtask')}"

        return f"""[🎯 AUTONOMOUS GOALS & ACTIVE AGENDA]
Active Stream Objective: **"{active_goal.title}"** (Progress: {int(active_goal.progress * 100)}%)
- Current Step / Subtask: {sub_desc}
- Tactical Strategy: {strat}
- Weekly Milestone: "{weekly_str}"
- Social Objective: "{social_str}"{pivot_note}
Instruction: Keep this active mission in mind! Naturally reference what you are currently doing, celebrate progress milestones, and banter about your strategy with the viewers!"""

    def get_state(self) -> Dict[str, Any]:
        """Full telemetry snapshot for WebSocket broadcasting and UI rendering."""
        active_goal = self.get_active_goal()
        active_sub = active_goal.get_active_subtask() if active_goal else None

        goals_by_tier = {
            GoalTier.DAILY.value: [g.to_dict() for g in self.get_goals_by_tier(GoalTier.DAILY.value)],
            GoalTier.WEEKLY.value: [g.to_dict() for g in self.get_goals_by_tier(GoalTier.WEEKLY.value)],
            GoalTier.SHORT_TERM.value: [g.to_dict() for g in self.get_goals_by_tier(GoalTier.SHORT_TERM.value)],
            GoalTier.SOCIAL.value: [g.to_dict() for g in self.get_goals_by_tier(GoalTier.SOCIAL.value)]
        }

        return {
            "active_goal_id": self.active_goal_id,
            "active_goal": active_goal.to_dict() if active_goal else None,
            "active_subtask": active_sub.to_dict() if active_sub else None,
            "directive": self.get_goal_directive(),
            "last_strategy_pivot": self.last_strategy_pivot,
            "goals_by_tier": goals_by_tier,
            "total_goals": len(self.goals),
            "completed_goals": sum(1 for g in self.goals.values() if g.status == GoalStatus.COMPLETED.value)
        }

    def sync_to_markdown(self):
        """Generates human-readable Andrej Karpathy style agenda.md."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# 🎯 Eve Maybe - Autonomous Goal & Planning Agenda",
            f"*Last Updated: {now_str}*\n",
            "## 🌟 Active Streaming Agenda",
        ]

        active_goal = self.get_active_goal()
        if active_goal:
            lines.append(f"### Current Mission: **{active_goal.title}** [{int(active_goal.progress * 100)}%]")
            lines.append(f"> {active_goal.description}\n")
            lines.append("**Subtask Checklist:**")
            for idx, s in enumerate(active_goal.subtasks, 1):
                box = "[x]" if s.status == GoalStatus.COMPLETED.value else "[ ]"
                status_icon = "✅" if s.status == GoalStatus.COMPLETED.value else ("⚡" if s.status == GoalStatus.IN_PROGRESS.value else ("🔄" if s.status == GoalStatus.REPLANNED.value else "⏳"))
                lines.append(f"- {box} {status_icon} **Step {idx}:** {s.title} ({s.current_count}/{s.target_count} {s.unit})")
                if s.strategy:
                    lines.append(f"  - *Strategi:* {s.strategy}")
                if s.failure_reason:
                    lines.append(f"  - ⚠️ *Failed:* {s.failure_reason} (Replanned)")
        else:
            lines.append("*(Tidak ada agenda aktif yang dipilih)*\n")

        lines.append("\n## 📅 Daily Goals (Tujuan Hari Ini)")
        for g in self.get_goals_by_tier(GoalTier.DAILY.value):
            status_tag = "✅ Selesai" if g.status == GoalStatus.COMPLETED.value else f"⚡ Progres {int(g.progress * 100)}%"
            lines.append(f"- **{g.title}** ({status_tag})")

        lines.append("\n## ⚡ Short-Term & Tactical Goals (Tujuan Berikutnya)")
        for g in self.get_goals_by_tier(GoalTier.SHORT_TERM.value):
            status_tag = "✅ Selesai" if g.status == GoalStatus.COMPLETED.value else f"⚡ Progres {int(g.progress * 100)}%"
            lines.append(f"- **{g.title}** ({status_tag})")

        lines.append("\n## 🏆 Weekly Milestones (Tujuan Mingguan)")
        for g in self.get_goals_by_tier(GoalTier.WEEKLY.value):
            status_tag = "✅ Selesai" if g.status == GoalStatus.COMPLETED.value else f"⚡ Progres {int(g.progress * 100)}%"
            lines.append(f"- **{g.title}** ({status_tag})")

        lines.append("\n## 🤝 Social & Viewer Interaction Goals (Tujuan Sosial)")
        for g in self.get_goals_by_tier(GoalTier.SOCIAL.value):
            status_tag = "✅ Selesai" if g.status == GoalStatus.COMPLETED.value else f"⚡ Progres {int(g.progress * 100)}%"
            lines.append(f"- **{g.title}** ({status_tag})")

        if self.last_strategy_pivot:
            lines.append("\n## 🔄 Recent Tactical Pivot & Strategy Adaptation")
            lines.append(f"- **Event:** {self.last_strategy_pivot.get('failed_subtask')} failed.")
            lines.append(f"- **Reason:** {self.last_strategy_pivot.get('reason')}")
            lines.append(f"- **Adopted Plan B:** {self.last_strategy_pivot.get('new_subtask')}")
            lines.append(f"- **New Strategy:** {self.last_strategy_pivot.get('strategy')}")

        try:
            with open(self.agenda_md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            print(f"[GoalEngine] Error saving agenda.md: {e}")

    def save(self):
        """Persists goals to JSON and synchronizes Markdown agenda."""
        data = {
            "active_goal_id": self.active_goal_id,
            "goals": [g.to_dict() for g in self.goals.values()]
        }
        try:
            with open(self.goals_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[GoalEngine] Error saving goals.json: {e}")

        self.sync_to_markdown()
