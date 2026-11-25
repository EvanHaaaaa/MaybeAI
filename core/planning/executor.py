import asyncio
import inspect
import math
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.planning.models import Goal, GoalCategory, GoalStatus, GoalTier, Subtask
from core.planning.engine import GoalEngine


class AutonomousMissionExecutor:
    """
    Closed-loop autonomous mission controller for Eve Maybe.
    Periodically (or on-demand via `step_once`) inspects the active goal and subtask,
    plans a concrete domain action (Minecraft, Chess, Performance, or Social),
    optionally gates execution behind human approval, executes the action closed-loop,
    evaluates/credits progress back into `GoalEngine` (syncing `agenda.md`),
    triggers `StrategyReplanner` on failure, and emits `mission.step` / `mission.status` events.
    """

    def __init__(
        self,
        goal_engine: GoalEngine,
        mood_engine: Optional[Any] = None,
        minecraft: Optional[Any] = None,
        chess: Optional[Any] = None,
        performance_runner: Optional[Callable[..., Any]] = None,
        speak_fn: Optional[Callable[..., Any]] = None,
        event_bus: Optional[Any] = None,
        human_approval_required: bool = False,
        tick_interval_sec: float = 25.0,
        enabled: bool = True,
    ):
        self.goal_engine = goal_engine
        self.mood_engine = mood_engine
        self.minecraft = minecraft
        self.chess = chess
        self.performance_runner = performance_runner
        self.speak_fn = speak_fn
        self.event_bus = event_bus
        self.human_approval_required = bool(human_approval_required)
        self.tick_interval_sec = max(0.05, float(tick_interval_sec))
        self.enabled = bool(enabled)

        self.is_running: bool = False
        self.is_paused: bool = False
        self.pending_approval: Optional[Dict[str, Any]] = None
        self.last_action: Optional[Dict[str, Any]] = None
        self.last_step_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.step_count: int = 0
        self.history: List[Dict[str, Any]] = []

        self._loop_task: Optional[asyncio.Task] = None
        self._step_lock = asyncio.Lock()

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _speak(self, text: str) -> None:
        if not self.speak_fn or not text:
            return
        try:
            await self._maybe_await(self.speak_fn(text))
        except Exception as exc:
            print(f"[AutonomousMissionExecutor] speak_fn error: {exc}")

    async def _emit_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        if not self.event_bus:
            return
        try:
            if hasattr(self.event_bus, "publish"):
                await self._maybe_await(self.event_bus.publish(event_name, payload))
            elif hasattr(self.event_bus, "emit"):
                await self._maybe_await(self.event_bus.emit(event_name, payload))
        except Exception as exc:
            print(f"[AutonomousMissionExecutor] EventBus emit error ({event_name}): {exc}")

    def _emit_event_sync(self, event_name: str, payload: Dict[str, Any]) -> None:
        if not self.event_bus:
            return
        try:
            if hasattr(self.event_bus, "publish_nowait"):
                self.event_bus.publish_nowait(event_name, payload)
                return
            loop = asyncio.get_running_loop()
            if hasattr(self.event_bus, "publish"):
                loop.create_task(self.event_bus.publish(event_name, payload))
        except RuntimeError:
            pass
        except Exception as exc:
            print(f"[AutonomousMissionExecutor] Sync emit error ({event_name}): {exc}")

    def _get_mood_dimensions(self) -> Optional[Dict[str, float]]:
        if self.mood_engine is None:
            return None
        if isinstance(self.mood_engine, dict):
            return self.mood_engine
        return getattr(self.mood_engine, "dimensions", None)

    def _infer_domain(self, goal: Goal, subtask: Subtask) -> str:
        """Maps a goal + subtask to one of: minecraft, chess, performance, social."""
        cat = (subtask.category or goal.category or "").lower()
        goal_cat = (goal.category or "").lower()
        text = f"{goal.title} {goal.description} {subtask.title} {subtask.description} {subtask.unit}".lower()

        if cat == GoalCategory.MINECRAFT.value or goal_cat == GoalCategory.MINECRAFT.value:
            return "minecraft"
        if cat == GoalCategory.CHESS.value or goal_cat == GoalCategory.CHESS.value:
            return "chess"
        if cat == GoalCategory.PERFORMANCE.value or goal_cat == GoalCategory.PERFORMANCE.value:
            return "performance"
        if cat == GoalCategory.SOCIAL.value or goal_cat == GoalCategory.SOCIAL.value or goal.tier == GoalTier.SOCIAL.value:
            return "social"

        if any(w in text for w in ["minecraft", "speedrun", "dragon", "iron", "oak", "log", "plank", "cobblestone", "mining", "rumah", "shelter", "torch", "blaze"]):
            return "minecraft"
        if any(w in text for w in ["catur", "chess", "skakmat", "opening", "grandmaster"]) or re.search(r"\belo\b", text):
            return "chess"
        if any(w in text for w in ["konser", "karaoke", "nyanyi", "lagu", "setlist", "glowstick", "encore", "performance", "idol"]):
            return "performance"
        return "social"

    def _compute_step_delta(self, subtask: Subtask) -> float:
        remaining = max(0.0, subtask.target_count - subtask.current_count)
        if remaining <= 0:
            return 1.0
        if subtask.target_count <= 4.0:
            return 1.0
        return float(min(remaining, max(1.0, math.ceil(subtask.target_count / 4.0))))

    def _extract_song_id(self, text: str) -> Optional[str]:
        known_songs = [
            "digital_world",
            "midnight_starlight",
            "glitch_overclock",
            "tsundere_anthem",
            "minecraft_creeper_lullaby",
        ]
        lower = text.lower()
        for song_id in known_songs:
            if song_id in lower or song_id.replace("_", " ") in lower:
                return song_id
        return None

    def _extract_target_elo(self, text: str) -> Optional[int]:
        match = re.search(r"\belo\s*(\d{3,4})\b", text.lower())
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _plan_action(self, goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        """Plans a concrete domain action for the active goal and subtask."""
        domain = self._infer_domain(goal, subtask)
        combined = f"{goal.title} {subtask.title} {subtask.description} {subtask.unit}".lower()
        delta = self._compute_step_delta(subtask)
        params: Dict[str, Any] = {"delta": delta}

        if domain == "minecraft":
            if any(w in combined for w in ["speedrun", "dragon", "nether", "portal", "blaze", "ender", "bucket"]):
                action_name = "minecraft_speedrun_advance"
                params["mode"] = "kompe"
            elif any(w in combined for w in ["guard", "lindungi", "shield", "perisai", "mob"]):
                action_name = "minecraft_guard"
                params["mode"] = "guard"
            else:
                action_name = "minecraft_casual_gather"
                params["mode"] = "santai"
                params["item"] = subtask.unit or "logs"
        elif domain == "chess":
            chess_active = bool(self.chess is not None and getattr(self.chess, "is_active", False))
            target_elo = self._extract_target_elo(combined)
            if not chess_active:
                action_name = "chess_start_game"
                params["elo"] = target_elo or getattr(getattr(self.chess, "engine", None), "elo", 1200)
                params["play_as"] = "white"
            else:
                action_name = "chess_play_move"
        elif domain == "performance":
            action_name = "perform_song"
            params["song_id"] = self._extract_song_id(combined)
        else:
            action_name = "social_outreach"
            params["topic"] = subtask.title

        return {
            "plan_id": f"plan_{uuid.uuid4().hex[:8]}",
            "goal_id": goal.id,
            "goal_title": goal.title,
            "subtask_id": subtask.id,
            "subtask_title": subtask.title,
            "subtask_unit": subtask.unit,
            "domain": domain,
            "action_name": action_name,
            "params": params,
            "strategy": subtask.strategy,
            "created_at": time.time(),
        }

    def _ensure_active_goal_and_subtask(self) -> Optional[tuple]:
        active_goal = self.goal_engine.get_active_goal()
        if (
            not active_goal
            or active_goal.status not in (GoalStatus.IN_PROGRESS.value, GoalStatus.PENDING.value)
            or active_goal.get_active_subtask() is None
        ):
            chosen, _ = self.goal_engine.autonomous_select_next_activity(self._get_mood_dimensions())
            active_goal = chosen

        if not active_goal:
            return None

        if active_goal.status == GoalStatus.PENDING.value:
            active_goal.status = GoalStatus.IN_PROGRESS.value

        active_sub = active_goal.get_active_subtask()
        if not active_sub:
            return None

        if active_sub.status == GoalStatus.PENDING.value:
            active_sub.status = GoalStatus.IN_PROGRESS.value
            self.goal_engine.save()

        return active_goal, active_sub

    async def _execute_minecraft(self, plan: Dict[str, Any], goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        params = plan["params"]
        action_name = plan["action_name"]
        delta = float(params.get("delta", 1.0))
        is_connected = bool(
            self.minecraft is not None
            and getattr(self.minecraft, "connection_status", "disconnected") == "connected"
        )

        if is_connected:
            mode = params.get("mode", "santai")
            if hasattr(self.minecraft, "set_mode") and getattr(self.minecraft, "current_mode", None) != mode:
                await self._maybe_await(self.minecraft.set_mode(mode))

            if action_name == "minecraft_speedrun_advance":
                adv_fn = getattr(self.minecraft, "advance_speedrun_phase", None) or getattr(self.minecraft, "advance_speedrun", None)
                if adv_fn:
                    await self._maybe_await(adv_fn())
                eval_res = self.goal_engine.evaluate_event("minecraft_speedrun_advance", {"connected": True, "delta": delta})
            elif action_name == "minecraft_guard":
                if hasattr(self.minecraft, "guard_player"):
                    await self._maybe_await(self.minecraft.guard_player(getattr(self.minecraft, "guard_target", None)))
                eval_res = self.goal_engine.evaluate_event("minecraft_guard_victory", {"connected": True, "delta": delta})
            else:
                if hasattr(self.minecraft, "toggle_wander"):
                    await self._maybe_await(self.minecraft.toggle_wander())
                elif hasattr(self.minecraft, "jump"):
                    await self._maybe_await(self.minecraft.jump())
                eval_res = self.goal_engine.evaluate_event(
                    "minecraft_item_collected",
                    {"item": params.get("item", "logs"), "count": delta, "connected": True},
                )
        else:
            commentary = (
                f"[emotion: happy] [Minecraft Expedition] Eve lagi jalanin misi '{subtask.title}' "
                f"({subtask.strategy or 'fokus kumpulin progres'})! [action: wink]"
            )
            await self._speak(commentary)
            if action_name == "minecraft_speedrun_advance":
                eval_res = self.goal_engine.evaluate_event("minecraft_speedrun_advance", {"simulated": True, "delta": delta})
            elif action_name == "minecraft_guard":
                eval_res = self.goal_engine.evaluate_event("minecraft_guard_victory", {"simulated": True, "delta": delta})
            else:
                eval_res = self.goal_engine.evaluate_event(
                    "minecraft_item_collected",
                    {"item": params.get("item", "logs"), "count": delta, "simulated": True},
                )

        if not eval_res.get("advanced"):
            eval_res = self.goal_engine.evaluate_event(
                "mission_subtask_executed",
                {"goal_id": goal.id, "subtask_id": subtask.id, "delta": delta, "domain": "minecraft"},
            )

        return {"success": True, "connected": is_connected, "mode": params.get("mode"), "eval": eval_res}

    async def _execute_chess(self, plan: Dict[str, Any], goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        params = plan["params"]
        action_name = plan["action_name"]

        if self.chess is not None:
            if action_name == "chess_start_game" and hasattr(self.chess, "start_game"):
                target_elo = int(params.get("elo") or 1200)
                play_as = params.get("play_as", "white")
                try:
                    sig = inspect.signature(self.chess.start_game)
                    sig_params = sig.parameters
                except (TypeError, ValueError):
                    sig_params = {}

                if "play_as" in sig_params:
                    await self._maybe_await(self.chess.start_game(elo=target_elo, play_as=play_as))
                elif "player_color" in sig_params:
                    await self._maybe_await(self.chess.start_game(player_name="ChatChallenger", player_color=play_as, elo=target_elo))
                else:
                    await self._maybe_await(self.chess.start_game(elo=target_elo, play_as=play_as))

                eval_res = self.goal_engine.evaluate_event("chess_game_started", {"elo": target_elo, "play_as": play_as})
            else:
                move_san = None
                if hasattr(self.chess, "make_bot_move"):
                    move_san = await self._maybe_await(self.chess.make_bot_move())
                elif hasattr(self.chess, "play_autonomous_move"):
                    move_san = await self._maybe_await(self.chess.play_autonomous_move())

                if not move_san:
                    await self._speak(
                        f"[emotion: smug] [Chess Tactical Drill] Eve mengasah taktik '{subtask.title}' — "
                        f"{subtask.strategy or 'kontrol petak tengah'}! [action: wink]"
                    )
                eval_res = self.goal_engine.evaluate_event("chess_move_played", {"san": move_san, "subtask": subtask.title})
        else:
            await self._speak(
                f"[emotion: smug] [Chess Focus] Eve lagi latihan catur mandiri untuk '{subtask.title}'! [action: wink]"
            )
            event_name = "chess_game_started" if action_name == "chess_start_game" else "chess_move_played"
            eval_res = self.goal_engine.evaluate_event(event_name, {"simulated": True})

        if not eval_res.get("advanced"):
            eval_res = self.goal_engine.evaluate_event(
                "mission_subtask_executed",
                {"goal_id": goal.id, "subtask_id": subtask.id, "delta": 1.0, "domain": "chess"},
            )

        return {"success": True, "action_name": action_name, "eval": eval_res}

    async def _execute_performance(self, plan: Dict[str, Any], goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        song_id = plan["params"].get("song_id")
        if self.performance_runner is not None:
            try:
                sig = inspect.signature(self.performance_runner)
                positional = [
                    p for p in sig.parameters.values()
                    if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                ]
                if positional:
                    runner_res = await self._maybe_await(self.performance_runner(song_id))
                else:
                    runner_res = await self._maybe_await(self.performance_runner())
            except (TypeError, ValueError):
                runner_res = await self._maybe_await(self.performance_runner(song_id))

            if isinstance(runner_res, dict) and runner_res.get("success") is False:
                return runner_res
        else:
            await self._speak(
                f"[emotion: excited] [Idol Stage] Eve bersiap tampil untuk '{subtask.title}'! "
                f"Ayo nyalakan glowstick kalian di chat! [action: wink]"
            )

        event_name = "glowsticks_reached" if "glowstick" in (subtask.unit or "").lower() else "performance_completed"
        eval_res = self.goal_engine.evaluate_event(event_name, {"song_id": song_id, "delta": 1.0})
        if not eval_res.get("advanced"):
            eval_res = self.goal_engine.evaluate_event(
                "mission_subtask_executed",
                {"goal_id": goal.id, "subtask_id": subtask.id, "delta": 1.0, "domain": "performance"},
            )
        return {"success": True, "song_id": song_id, "eval": eval_res}

    async def _execute_social(self, plan: Dict[str, Any], goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        outreach_prompt = (
            f"[emotion: happy] Halo semuanya! {subtask.title} — ada penonton baru atau yang lagi mampir santai? "
            f"Cerita dong kalian suka game atau lagu apa, Eve lagi jalanin misi '{goal.title}' nih! [action: wink]"
        )
        await self._speak(outreach_prompt)
        eval_res = self.goal_engine.evaluate_event(
            "player_greeted",
            {"source": "autonomous_outreach", "subtask": subtask.title},
        )
        if not eval_res.get("advanced"):
            eval_res = self.goal_engine.evaluate_event(
                "mission_subtask_executed",
                {"goal_id": goal.id, "subtask_id": subtask.id, "delta": 1.0, "domain": "social"},
            )
        return {"success": True, "prompt": outreach_prompt, "eval": eval_res}

    async def _execute_domain_action(self, plan: Dict[str, Any], goal: Goal, subtask: Subtask) -> Dict[str, Any]:
        domain = plan["domain"]
        if domain == "minecraft":
            return await self._execute_minecraft(plan, goal, subtask)
        if domain == "chess":
            return await self._execute_chess(plan, goal, subtask)
        if domain == "performance":
            return await self._execute_performance(plan, goal, subtask)
        return await self._execute_social(plan, goal, subtask)

    def _record_step(self, step_payload: Dict[str, Any]) -> None:
        self.last_action = step_payload
        self.last_step_at = time.time()
        self.step_count += 1
        self.history.append(step_payload)
        if len(self.history) > 50:
            self.history = self.history[-50:]

    async def step_once(self, force: bool = False) -> Dict[str, Any]:
        """
        Executes a single closed-loop mission tick:
        select goal -> plan domain action -> optional approval gate -> execute -> evaluate & sync agenda.md.
        """
        if self.is_paused and not force:
            status_payload = self.get_status()
            await self._emit_event("mission.status", status_payload)
            return {"status": "paused", "executed": False, "reason": "Executor is paused"}

        async with self._step_lock:
            selected = self._ensure_active_goal_and_subtask()
            if not selected:
                status_payload = self.get_status()
                await self._emit_event("mission.status", status_payload)
                return {"status": "idle", "executed": False, "reason": "No active goal or subtask"}

            active_goal, active_sub = selected

            if self.human_approval_required and not force:
                if self.pending_approval is None:
                    self.pending_approval = self._plan_action(active_goal, active_sub)
                status_payload = self.get_status()
                await self._emit_event("mission.status", status_payload)
                return {
                    "status": "awaiting_approval",
                    "executed": False,
                    "pending_approval": dict(self.pending_approval),
                    "goal": active_goal.to_dict(),
                    "subtask": active_sub.to_dict(),
                }

            plan = self.pending_approval if (force and self.pending_approval is not None) else self._plan_action(active_goal, active_sub)
            self.pending_approval = None

            try:
                domain_result = await self._execute_domain_action(plan, active_goal, active_sub)
                if isinstance(domain_result, dict) and domain_result.get("success") is False:
                    raise RuntimeError(domain_result.get("error") or domain_result.get("reason") or "Mission step failed")

                eval_details = (domain_result or {}).get("eval", {}).get("details", {})
                if self.mood_engine and hasattr(self.mood_engine, "apply_stimulus"):
                    if eval_details.get("goal_completed"):
                        self.mood_engine.apply_stimulus("goal_all_completed")
                    elif eval_details.get("subtask_completed"):
                        self.mood_engine.apply_stimulus("goal_milestone_completed")

                self.last_error = None
                self.goal_engine.save()

                updated_goal = self.goal_engine.get_active_goal()
                step_payload = {
                    "status": "executed",
                    "executed": True,
                    "plan_id": plan["plan_id"],
                    "domain": plan["domain"],
                    "action_name": plan["action_name"],
                    "goal_id": active_goal.id,
                    "goal_title": active_goal.title,
                    "subtask_id": active_sub.id,
                    "subtask_title": active_sub.title,
                    "subtask_completed": bool(eval_details.get("subtask_completed", False)),
                    "goal_completed": bool(eval_details.get("goal_completed", False)),
                    "goal_progress": updated_goal.progress if updated_goal else active_goal.progress,
                    "timestamp": time.time(),
                }
                self._record_step(step_payload)

                await self._emit_event("goal.updated", self.goal_engine.get_state())
                await self._emit_event("mission.step", step_payload)
                await self._emit_event("mission.status", self.get_status())
                return {
                    **step_payload,
                    "domain_result": domain_result,
                    "goal": updated_goal.to_dict() if updated_goal else active_goal.to_dict(),
                }

            except Exception as exc:
                reason = str(exc) or f"{plan['domain']} execution failed"
                self.last_error = reason
                new_sub, replan_speech = self.goal_engine.fail_and_replan_active_subtask(reason)
                if self.mood_engine and hasattr(self.mood_engine, "apply_stimulus"):
                    self.mood_engine.apply_stimulus("goal_strategy_failed")
                if replan_speech:
                    await self._speak(replan_speech)
                self.goal_engine.save()

                updated_goal = self.goal_engine.get_active_goal()
                step_payload = {
                    "status": "replanned",
                    "executed": False,
                    "replanned": True,
                    "plan_id": plan["plan_id"],
                    "domain": plan["domain"],
                    "action_name": plan["action_name"],
                    "goal_id": active_goal.id,
                    "goal_title": active_goal.title,
                    "failed_subtask_id": active_sub.id,
                    "failed_subtask_title": active_sub.title,
                    "error": reason,
                    "new_subtask": new_sub.to_dict() if new_sub else None,
                    "replan_speech": replan_speech,
                    "timestamp": time.time(),
                }
                self._record_step(step_payload)

                await self._emit_event("goal.updated", self.goal_engine.get_state())
                await self._emit_event("mission.step", step_payload)
                await self._emit_event("mission.status", self.get_status())
                return {
                    **step_payload,
                    "goal": updated_goal.to_dict() if updated_goal else active_goal.to_dict(),
                }

    async def _run_loop(self) -> None:
        while self.is_running:
            await asyncio.sleep(self.tick_interval_sec)
            if not self.is_running:
                break
            if not self.enabled or self.is_paused or self.pending_approval is not None:
                continue
            try:
                await self.step_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                print(f"[AutonomousMissionExecutor] Loop error: {exc}")

    async def start_loop(self) -> bool:
        """Starts the periodic closed-loop autonomous mission background task."""
        if self.is_running and self._loop_task and not self._loop_task.done():
            return True
        self.is_running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        await self._emit_event("mission.status", self.get_status())
        return True

    async def stop_loop(self) -> None:
        """Gracefully stops the autonomous mission background loop."""
        self.is_running = False
        task = self._loop_task
        self._loop_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._emit_event("mission.status", self.get_status())

    def pause(self) -> Dict[str, Any]:
        """Pauses autonomous mission loop execution."""
        self.is_paused = True
        status = self.get_status()
        self._emit_event_sync("mission.status", status)
        return status

    def resume(self) -> Dict[str, Any]:
        """Resumes autonomous mission loop execution."""
        self.is_paused = False
        status = self.get_status()
        self._emit_event_sync("mission.status", status)
        return status

    async def approve_pending(self) -> Dict[str, Any]:
        """Approves and immediately executes the currently queued mission action."""
        if not self.pending_approval:
            return {"status": "no_pending", "executed": False}
        return await self.step_once(force=True)

    async def reject_pending(self, reason: str = "Rejected by creator") -> Dict[str, Any]:
        """Rejects and clears the currently queued mission action."""
        if not self.pending_approval:
            return {"status": "no_pending", "executed": False}
        rejected = self.pending_approval
        self.pending_approval = None
        step_payload = {
            "status": "rejected",
            "executed": False,
            "plan_id": rejected.get("plan_id"),
            "domain": rejected.get("domain"),
            "action_name": rejected.get("action_name"),
            "reason": reason,
            "timestamp": time.time(),
        }
        self._record_step(step_payload)
        await self._emit_event("mission.status", self.get_status())
        return {**step_payload, "rejected_plan": rejected}

    def update_config(
        self,
        enabled: Optional[bool] = None,
        human_approval_required: Optional[bool] = None,
        tick_interval_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Updates runtime executor settings safely."""
        if enabled is not None:
            self.enabled = bool(enabled)
        if human_approval_required is not None:
            self.human_approval_required = bool(human_approval_required)
        if tick_interval_sec is not None:
            self.tick_interval_sec = max(0.05, float(tick_interval_sec))
        status = self.get_status()
        self._emit_event_sync("mission.status", status)
        return status

    def get_status(self) -> Dict[str, Any]:
        """Returns a JSON-serializable telemetry snapshot of the mission executor."""
        active_goal = self.goal_engine.get_active_goal()
        active_sub = active_goal.get_active_subtask() if active_goal else None
        return {
            "enabled": self.enabled,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "human_approval_required": self.human_approval_required,
            "tick_interval_sec": self.tick_interval_sec,
            "step_count": self.step_count,
            "last_step_at": self.last_step_at,
            "last_error": self.last_error,
            "pending_approval": dict(self.pending_approval) if self.pending_approval else None,
            "last_action": dict(self.last_action) if self.last_action else None,
            "active_goal_id": active_goal.id if active_goal else None,
            "active_goal_title": active_goal.title if active_goal else None,
            "active_goal_category": active_goal.category if active_goal else None,
            "active_goal_progress": active_goal.progress if active_goal else 0.0,
            "active_subtask_id": active_sub.id if active_sub else None,
            "active_subtask_title": active_sub.title if active_sub else None,
            "history": list(self.history[-10:]),
        }
