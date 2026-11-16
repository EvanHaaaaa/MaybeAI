from typing import Dict, Any, List, Optional, Tuple
from core.minecraft.multiplayer.models import Team, TeamRole
from core.minecraft.multiplayer.contribution_ledger import ContributionLedger


class TeamManager:
    """
    Manages Minecraft multiplayer squads, factions, role assignments,
    and autonomous expedition partner selection.
    """

    def __init__(self):
        self.teams: Dict[str, Team] = {}
        self.active_team_id: Optional[str] = None
        self._seed_default_squad()

    def _seed_default_squad(self):
        squad = Team(
            id="team_squad_maybe",
            name="Squad Maybe ✨",
            motto="Satu server, satu impian, bagi hasil diamond 50%!",
            leader="EveMaybe",
            members=["EveMaybe", "DiamondHunter", "Alex", "Steve"],
            member_roles={
                "EveMaybe": TeamRole.COMMANDER.value,
                "DiamondHunter": TeamRole.MINER.value,
                "Alex": TeamRole.VANGUARD.value,
                "Steve": TeamRole.BUILDER.value
            },
            treasury={"diamond": 8, "iron_ingot": 45, "bread": 28, "torch": 64},
            active_mission="Ekspedisi Tambang Gua Y=-58 & Proyek Rumah Kaca"
        )
        self.teams[squad.id] = squad
        self.active_team_id = squad.id

    def get_active_team(self) -> Optional[Team]:
        if self.active_team_id and self.active_team_id in self.teams:
            return self.teams[self.active_team_id]
        if self.teams:
            return next(iter(self.teams.values()))
        return None

    def create_team(self, name: str, motto: str = "", leader: str = "EveMaybe") -> Team:
        team = Team(name=name, motto=motto, leader=leader)
        team.add_member(leader, TeamRole.COMMANDER.value)
        self.teams[team.id] = team
        self.active_team_id = team.id
        return team

    def add_member(self, team_id: str, player_name: str, role: str = TeamRole.SCOUT.value) -> bool:
        team = self.teams.get(team_id)
        if team:
            team.add_member(player_name, role)
            return True
        return False

    def remove_member(self, team_id: str, player_name: str) -> bool:
        team = self.teams.get(team_id)
        if team:
            team.remove_member(player_name)
            return True
        return False

    def assign_role(self, team_id: str, player_name: str, role: str) -> bool:
        team = self.teams.get(team_id)
        if team and player_name in team.members:
            team.member_roles[player_name] = role
            return True
        return False

    def select_expedition_partner(
        self,
        mission_type: str,
        ledger: ContributionLedger
    ) -> Tuple[str, float, str]:
        """
        Autonomously selects the best partner from current squad / server members
        and returns (partner_name, fitness_score, eve_invitation_speech).
        """
        team = self.get_active_team()
        candidate_pool = [m for m in team.members if m.lower() != "evemaybe"] if team else list(ledger.players.keys())

        if not candidate_pool:
            candidate_pool = [p.player_name for p in ledger.players.values() if p.player_name.lower() != "evemaybe"]

        scored: List[Tuple[str, float]] = []
        for cand in candidate_pool:
            score = ledger.evaluate_partner_fitness(cand, mission_type)
            scored.append((cand, score))

        # Sort descending by fitness
        scored.sort(key=lambda x: x[1], reverse=True)
        best_cand, best_score = scored[0] if scored else ("DiamondHunter", 85.0)

        # Generate Eve's lively invitation speech
        m_lower = mission_type.lower()
        if "mining" in m_lower or "diamond" in m_lower or "cave" in m_lower:
            speech = f"[emotion: happy] {best_cand}! Dari kalkulasi reputasi mining ({int(best_score)}%), kamu partner paling hoki di squad. Ayo kawal aku ke celah gua Y=-58 buat panen diamond! [action: wink]"
        elif "combat" in m_lower or "nether" in m_lower or "raid" in m_lower:
            speech = f"[emotion: smug] {best_cand}! Senjata dan perisaimu paling teruji ({int(best_score)}%). Kamu maju di sampingku jadi vanguard ekspedisi Nether ya! [action: wink]"
        elif "build" in m_lower or "house" in m_lower or "base" in m_lower:
            speech = f"[emotion: happy] {best_cand}! Kreativitas arsitekturmu ({int(best_score)}%) paling juara di server. Temenin aku bangun base impian squad kita yuk! [action: giggle]"
        else:
            speech = f"[emotion: happy] {best_cand}! Kamu partner paling pas buat misi ini ({int(best_score)}%). Ayo jalan bareng Eve sekarang! [action: wink]"

        return best_cand, best_score, speech

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_team_id": self.active_team_id,
            "teams": [t.to_dict() for t in self.teams.values()]
        }

    def load_from_dict(self, data: Dict[str, Any]):
        self.active_team_id = data.get("active_team_id")
        for t_data in data.get("teams", []):
            team = Team.from_dict(t_data)
            self.teams[team.id] = team
