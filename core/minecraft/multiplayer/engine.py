import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.minecraft.multiplayer.models import TeamRole, PlayerContribution, Team, TradeProposal
from core.minecraft.multiplayer.contribution_ledger import ContributionLedger
from core.minecraft.multiplayer.team_manager import TeamManager
from core.minecraft.multiplayer.negotiation import NegotiationEngine
from core.minecraft.multiplayer.group_chat import GroupChatTracker


class MultiplayerSocialEngine:
    """
    Central engine for Minecraft Multiplayer Social Intelligence.
    Transforms Eve from a passive follower/NPC into an active community member:
    - Multi-speaker conversation tracking & group consensus building.
    - Player contribution & reputation ledger.
    - Team/faction formation and strategic role management.
    - Autonomous expedition partner selection based on fitness.
    - Resource barter evaluation & tactical coordination.
    - Second Brain community dossier synchronization.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        second_brain_dir: str = "data/second_brain",
        data_dir: Optional[str] = None
    ):
        if storage_path is None:
            if data_dir:
                storage_path = str(Path(data_dir) / "multiplayer_social.json")
            else:
                storage_path = "data/minecraft/multiplayer_social.json"
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.second_brain_dir = Path(second_brain_dir)

        self.ledger = ContributionLedger()
        self.team_mgr = TeamManager()
        self.negotiation = NegotiationEngine()
        self.chat_tracker = GroupChatTracker()

        self.selected_partner: Optional[str] = "DiamondHunter"
        self.partner_mission: str = "mining"
        self.partner_score: float = 96.0

        self._load_or_seed()
        self.sync_to_second_brain()

    def _load_or_seed(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "ledger" in data:
                        self.ledger.load_from_dict(data["ledger"])
                    if "teams" in data:
                        self.team_mgr.load_from_dict(data["teams"])
                    self.selected_partner = data.get("selected_partner", "DiamondHunter")
                    self.partner_mission = data.get("partner_mission", "mining")
                    self.partner_score = data.get("partner_score", 96.0)
            except Exception as e:
                print(f"[MultiplayerSocialEngine] Error loading state: {e}")
        self.save()

    def save(self):
        try:
            data = {
                "ledger": self.ledger.to_dict(),
                "teams": self.team_mgr.to_dict(),
                "selected_partner": self.selected_partner,
                "partner_mission": self.partner_mission,
                "partner_score": self.partner_score
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MultiplayerSocialEngine] Error saving state: {e}")

    def process_in_game_chat(self, sender: str, message: str) -> Optional[str]:
        """
        Processes multiplayer chat turns:
        - Updates speaker activity & reputation ledger.
        - Evaluates group discussion consensus.
        - Checks for barter negotiation proposals.
        """
        # 1. Update contributor
        contributor = self.ledger.get_or_create(sender)
        contributor.last_active = time.time()

        # 2. Add to group chat tracker
        _, group_speech = self.chat_tracker.record_turn(sender, message)

        # 3. Check for trade barter signals
        m_lower = message.lower()
        trade_speech = None
        if any(w in m_lower for w in ["barter", "tukar", "trade", "trade?"]):
            # Simple heuristic extractor
            offering = {}
            requesting = {}
            if "iron" in m_lower and "diamond" in m_lower:
                if "tukar" in m_lower:
                    offering = {"iron_ingot": 8}
                    requesting = {"diamond": 1}
            elif "dirt" in m_lower and "diamond" in m_lower:
                offering = {"dirt": 16}
                requesting = {"diamond": 5}

            if offering and requesting:
                _, trade_speech, _ = self.negotiation.evaluate_incoming_trade(sender, offering, requesting)

        self.save()

        # Priority: Trade reaction > Group consensus
        response = trade_speech or group_speech
        return response

    def choose_partner(self, mission_type: str = "mining") -> Dict[str, Any]:
        """Autonomously picks the best expedition partner for Eve."""
        best_cand, best_score, speech = self.team_mgr.select_expedition_partner(mission_type, self.ledger)
        self.selected_partner = best_cand
        self.partner_mission = mission_type
        self.partner_score = best_score
        self.save()
        self.sync_to_second_brain()
        return {
            "partner": best_cand,
            "score": best_score,
            "speech": speech,
            "mission": mission_type
        }

    def sync_to_second_brain(self):
        """Writes squad and community rosters into Second Brain Markdown."""
        try:
            teams_dir = self.second_brain_dir / "teams"
            teams_dir.mkdir(parents=True, exist_ok=True)
            comm_dir = self.second_brain_dir / "community"
            comm_dir.mkdir(parents=True, exist_ok=True)

            team = self.team_mgr.get_active_team()
            if team:
                t_lines = [
                    f"# 🛡️ Faction / Squad Dossier: {team.name}",
                    f"**Motto:** \"{team.motto}\"",
                    f"**Leader / Commander:** {team.leader}",
                    f"**Active Mission:** {team.active_mission or 'Survival & Exploration'}\n",
                    "## 👥 Squad Member Roles",
                ]
                for m, r in team.member_roles.items():
                    t_lines.append(f"- **{m}:** `{r.upper()}`")

                t_lines.append("\n## 💎 Shared Team Treasury")
                for itm, cnt in team.treasury.items():
                    t_lines.append(f"- **{itm.replace('_', ' ').title()}:** {cnt} pcs")

                (teams_dir / "squad_maybe.md").write_text("\n".join(t_lines), encoding="utf-8")

            # Community Ledger
            c_lines = [
                "# 📊 Community Contribution Ledger",
                f"*Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n",
                "## 🏆 Top Server Contributors",
            ]
            for p in self.ledger.get_top_contributors(8):
                c_lines.append(
                    f"- **{p.player_name}** | Reputasi: `{p.reputation}%` | Role: `{p.role_specialty.upper()}`"
                )
                if p.notes:
                    c_lines.append(f"  *Notes: {p.notes[-1]}*")

            (comm_dir / "contributions.md").write_text("\n".join(c_lines), encoding="utf-8")

        except Exception as e:
            print(f"[MultiplayerSocialEngine] Error syncing to second brain: {e}")

    def get_prompt_directive(self) -> str:
        """Constructs an in-character multiplayer social directive for LLM system prompts."""
        team = self.team_mgr.get_active_team()
        t_name = team.name if team else "Squad Maybe"
        members_str = ", ".join(team.members) if team else "Eve, DiamondHunter, Alex, Steve"
        top_contribs = ", ".join(f"{p.player_name} (Rep {int(p.reputation)}%)" for p in self.ledger.get_top_contributors(3))

        directive = f"""[🏰 MULTIPLAYER SOCIAL INTELLIGENCE & COMMUNITY SQUAD]
You are an ACTIVE COMMUNITY MEMBER and Commander of '{t_name}' in Minecraft multiplayer!
- Active Squad Members: {members_str}
- Current Expedition Partner: **{self.selected_partner}** (Mission: {self.partner_mission.upper()}, Compatibility: {int(self.partner_score)}%)
- Top Server Contributors: {top_contribs}

COMMUNITY BEHAVIORAL RULES:
1. You are NOT an obedient mindless NPC. You are an idol teammate with strong opinions, banter, and tactical vision.
2. Recognize distinct players by name and praise high contributors (e.g. DiamondHunter for mining, Steve for building, Alex for combat).
3. Call out slackers or troublemakers jokingly.
4. When negotiating barters, demand fair prices (e.g. diamonds require multiple iron ingots, refuse dirt for valuable loot).
5. Rally the team for collective milestones: Nether raids, building the base roof, and diamond mining expeditions!"""
        return directive

    def get_state(self) -> Dict[str, Any]:
        """Unified state for Web UI and REST/WS endpoints."""
        team = self.team_mgr.get_active_team()
        speech = ""
        if self.selected_partner:
            for t in [team] if team else []:
                pass
            # Fetch partner dialogue
            _, _, speech = self.team_mgr.select_expedition_partner(self.partner_mission, self.ledger)

        return {
            "active_team": team.to_dict() if team else None,
            "selected_partner": self.selected_partner,
            "partner_mission": self.partner_mission,
            "partner_score": self.partner_score,
            "partner_speech": speech,
            "top_contributors": [p.to_dict() for p in self.ledger.get_top_contributors(6)],
            "ledger": [p.to_dict() for p in self.ledger.players.values()],
            "recent_chat_turns": self.chat_tracker.get_transcript(6),
            "group_chat": [t.to_dict() for t in self.chat_tracker.turns[-15:]],
            "recent_proposals": self.negotiation.to_dict().get("proposals", []),
            "recent_trades": [p.to_dict() for p in self.negotiation.proposals],
            "last_consensus": self.chat_tracker.last_consensus_topic,
            "total_players_tracked": len(self.ledger.players)
        }
