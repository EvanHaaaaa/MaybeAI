import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


class TeamRole(str, Enum):
    COMMANDER = "commander"  # Pemimpin / Maskot Squad (Eve Maybe)
    MINER = "miner"          # Spesialis tambang bawah tanah (DiamondHunter)
    BUILDER = "builder"      # Arsitek & konstruksi markas (Steve)
    VANGUARD = "vanguard"    # Petarung garda depan / Pelindung tim (Alex)
    SCOUT = "scout"          # Penjelajah bioma & pencari dungeon


@dataclass
class PlayerContribution:
    player_name: str
    reputation: float = 75.0               # 0.0 to 100.0 (Skor reputasi di komunitas)
    role_specialty: str = TeamRole.SCOUT.value
    items_donated: Dict[str, int] = field(default_factory=dict)
    mobs_killed_for_team: int = 0
    structures_built: int = 0
    times_saved_eve: int = 0
    times_attacked_eve: int = 0
    notes: List[str] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)

    def add_donation(self, item: str, count: int = 1):
        clean_item = item.lower().strip()
        self.items_donated[clean_item] = self.items_donated.get(clean_item, 0) + count
        # Boost reputation based on item value
        if "diamond" in clean_item:
            self.reputation = min(100.0, self.reputation + count * 3.5)
        elif "iron" in clean_item:
            self.reputation = min(100.0, self.reputation + count * 1.0)
        else:
            self.reputation = min(100.0, self.reputation + count * 0.4)
        self.last_active = time.time()

    def record_combat_help(self, mob_name: str):
        self.mobs_killed_for_team += 1
        self.reputation = min(100.0, self.reputation + 2.5)
        self.notes.append(f"Membantu membunuh {mob_name} untuk tim")
        if len(self.notes) > 8:
            self.notes = self.notes[-8:]
        self.last_active = time.time()

    def record_pvp_strike(self, damage: float):
        self.times_attacked_eve += 1
        self.reputation = max(0.0, self.reputation - damage * 3.0)
        self.notes.append(f"Menyerang anggota tim / Eve (-{damage} HP)")
        if len(self.notes) > 8:
            self.notes = self.notes[-8:]
        self.last_active = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_name": self.player_name,
            "reputation": round(self.reputation, 1),
            "role_specialty": self.role_specialty,
            "items_donated": self.items_donated,
            "mobs_killed_for_team": self.mobs_killed_for_team,
            "structures_built": self.structures_built,
            "times_saved_eve": self.times_saved_eve,
            "times_attacked_eve": self.times_attacked_eve,
            "notes": self.notes,
            "last_active_str": time.strftime("%H:%M:%S", time.localtime(self.last_active))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerContribution":
        clean = {k: v for k, v in data.items() if k != "last_active_str"}
        return cls(**clean)


@dataclass
class Team:
    id: str = field(default_factory=lambda: f"team_{uuid.uuid4().hex[:6]}")
    name: str = "Squad Maybe ✨"
    motto: str = "Satu server, satu impian, bagi hasil diamond 50%!"
    leader: str = "EveMaybe"
    members: List[str] = field(default_factory=list)
    member_roles: Dict[str, str] = field(default_factory=dict)
    treasury: Dict[str, int] = field(default_factory=dict)
    active_mission: Optional[str] = "Membangun Markas Bersama & Ekspedisi Gua"
    created_at: float = field(default_factory=time.time)

    def add_member(self, player_name: str, role: str = TeamRole.SCOUT.value):
        if player_name not in self.members:
            self.members.append(player_name)
        self.member_roles[player_name] = role

    def remove_member(self, player_name: str):
        if player_name in self.members:
            self.members.remove(player_name)
        self.member_roles.pop(player_name, None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Team":
        return cls(**data)


@dataclass
class TradeProposal:
    id: str = field(default_factory=lambda: f"trade_{uuid.uuid4().hex[:6]}")
    proposer: str = "Steve"
    target: str = "EveMaybe"
    offering: Dict[str, int] = field(default_factory=dict)     # Contoh: {"iron_ingot": 8}
    requesting: Dict[str, int] = field(default_factory=dict)   # Contoh: {"diamond": 1}
    status: str = "pending"   # "pending", "accepted", "countered", "rejected"
    eve_verdict: str = "Evaluating barter..."
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "proposer": self.proposer,
            "target": self.target,
            "offering": self.offering,
            "requesting": self.requesting,
            "status": self.status,
            "eve_verdict": self.eve_verdict,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeProposal":
        clean = {k: v for k, v in data.items() if k != "time_str"}
        return cls(**clean)


@dataclass
class GroupDiscussionTurn:
    speaker: str
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker,
            "message": self.message,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupDiscussionTurn":
        clean = {k: v for k, v in data.items() if k != "time_str"}
        return cls(**clean)
