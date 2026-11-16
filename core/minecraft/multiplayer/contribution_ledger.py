from typing import Dict, Any, List, Optional
from core.minecraft.multiplayer.models import PlayerContribution, TeamRole


class ContributionLedger:
    """
    Tracks and evaluates individual player contributions, shared loot,
    combat aid, building work, and community reputation across the multiplayer server.
    """

    def __init__(self):
        self.players: Dict[str, PlayerContribution] = {}
        self._seed_default_contributors()

    def _seed_default_contributors(self):
        """Seeds canonical server members with realistic history."""
        # 1. DiamondHunter (Chief Mining Partner)
        p1 = PlayerContribution(
            player_name="DiamondHunter",
            reputation=96.0,
            role_specialty=TeamRole.MINER.value,
            items_donated={"diamond": 14, "iron_ingot": 64, "coal": 32},
            mobs_killed_for_team=8,
            times_saved_eve=2,
            notes=["Sering membagi hasil tambang diamond ke kas Eve", "Pandai menemukan celah gua Y=-58"]
        )
        self.players["diamondhunter"] = p1

        # 2. Alex (Vanguard Guardian)
        p2 = PlayerContribution(
            player_name="Alex",
            reputation=92.0,
            role_specialty=TeamRole.VANGUARD.value,
            items_donated={"golden_apple": 2, "iron_sword": 1, "cooked_beef": 20},
            mobs_killed_for_team=24,
            times_saved_eve=4,
            notes=["Selalu berada di garis depan saat diserbu creeper", "Perisai andalan saat ekspedisi gua malam hari"]
        )
        self.players["alex"] = p2

        # 3. Steve (Master Builder)
        p3 = PlayerContribution(
            player_name="Steve",
            reputation=88.0,
            role_specialty=TeamRole.BUILDER.value,
            items_donated={"oak_log": 96, "glass": 48, "cobblestone": 128},
            structures_built=5,
            notes=["Membangun dinding pelindung base dan atap kaca", "Menyediakan stok kayu tak terbatas"]
        )
        self.players["steve"] = p3

        # 4. GrieferGarry (Rival / Chaos Agent)
        p4 = PlayerContribution(
            player_name="GrieferGarry",
            reputation=38.0,
            role_specialty=TeamRole.SCOUT.value,
            items_donated={"dirt": 16},
            times_attacked_eve=3,
            notes=["Pernah memukul Eve di dekat jurang", "Suka barter tidak masuk akal (1 dirt minta 5 diamond)"]
        )
        self.players["griefergarry"] = p4

    def get_or_create(self, player_name: str) -> PlayerContribution:
        clean = player_name.strip() or "Player"
        key = clean.lower()
        if key not in self.players:
            self.players[key] = PlayerContribution(player_name=clean)
        return self.players[key]

    def record_donation(self, player_name: str, item: str, count: int = 1) -> PlayerContribution:
        prof = self.get_or_create(player_name)
        prof.add_donation(item, count)
        return prof

    def record_combat_aid(self, player_name: str, mob_name: str) -> PlayerContribution:
        prof = self.get_or_create(player_name)
        prof.record_combat_help(mob_name)
        return prof

    def record_building_help(self, player_name: str, task: str) -> PlayerContribution:
        prof = self.get_or_create(player_name)
        prof.structures_built += 1
        prof.reputation = min(100.0, prof.reputation + 2.0)
        prof.notes.append(f"Membantu pengerjaan: {task}")
        if len(prof.notes) > 8:
            prof.notes = prof.notes[-8:]
        return prof

    def record_pvp(self, player_name: str, damage: float) -> PlayerContribution:
        prof = self.get_or_create(player_name)
        prof.record_pvp_strike(damage)
        return prof

    def get_top_contributors(self, limit: int = 5) -> List[PlayerContribution]:
        return sorted(self.players.values(), key=lambda p: p.reputation, reverse=True)[:limit]

    def evaluate_partner_fitness(self, player_name: str, mission_type: str = "mining") -> float:
        """
        Calculates a compatibility fitness score [0.0 - 100.0] for teaming up with Eve
        on a specific mission (mining, nether/combat, base_building, scouting).
        """
        prof = self.get_or_create(player_name)
        base = prof.reputation * 0.5  # Base from general reputation (max 50)

        # Penalty for hostility
        if prof.times_attacked_eve > 0:
            base -= prof.times_attacked_eve * 15.0

        m_lower = mission_type.lower()
        if "mining" in m_lower or "cave" in m_lower or "diamond" in m_lower:
            if prof.role_specialty == TeamRole.MINER.value:
                base += 35.0
            dia_count = prof.items_donated.get("diamond", 0)
            base += min(15.0, dia_count * 1.5)

        elif "combat" in m_lower or "nether" in m_lower or "raid" in m_lower or "guard" in m_lower:
            if prof.role_specialty == TeamRole.VANGUARD.value:
                base += 35.0
            base += min(15.0, prof.mobs_killed_for_team * 0.8)
            base += min(10.0, prof.times_saved_eve * 2.5)

        elif "build" in m_lower or "house" in m_lower or "base" in m_lower:
            if prof.role_specialty == TeamRole.BUILDER.value:
                base += 35.0
            base += min(15.0, prof.structures_built * 3.0)

        else:
            if prof.role_specialty == TeamRole.SCOUT.value:
                base += 35.0

        return max(0.0, min(100.0, round(base, 1)))

    def to_dict(self) -> Dict[str, Any]:
        return {k: p.to_dict() for k, p in self.players.items()}

    def load_from_dict(self, data: Dict[str, Any]):
        for k, v in data.items():
            self.players[k.lower()] = PlayerContribution.from_dict(v)
