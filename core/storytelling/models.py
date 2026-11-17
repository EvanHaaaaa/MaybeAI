import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional


class StoryGenre(str, Enum):
    FANTASY_RPG = "fantasy_rpg"
    CYBERPUNK_HEIST = "cyberpunk_heist"
    MINECRAFT_QUEST = "minecraft_quest"
    ISEKAI_COMEDY = "isekai_comedy"
    MYSTERY_HORROR = "mystery_horror"
    CUSTOM = "custom"


class EveRole(str, Enum):
    DUNGEON_MASTER = "dungeon_master"        # DM / Narator dunia
    PARTY_MAGE = "party_mage"                # Anggota party penyihir tsundere
    PARTY_ROGUE = "party_rogue"              # Anggota party pencuri jahil
    ECCENTRIC_NPC = "eccentric_npc"          # NPC pedagang aneh / pemilik kedai
    VILLAIN_BOSS = "villain_boss"            # Ratu iblis / antagonis kocak


class CampaignStatus(str, Enum):
    IDLE = "idle"                            # Belum dimulai / selesai
    ACTIVE = "active"                        # Cerita sedang berjalan
    VOTING = "voting"                        # Menunggu voting keputusan chat
    DICE_ROLL = "dice_roll"                  # Menunggu lemparan dadu D20
    COMPLETED = "completed"                  # Campaign episode selesai


@dataclass
class StoryChoice:
    id: str                                  # e.g. "opt_1", "opt_2", "opt_3"
    label: str                               # e.g. "Menyelinap lewat bayangan"
    description: str                         # Penjelasan pilihan tindakan
    dc_check: Optional[int] = None           # Target Difficulty Class (e.g. DC 12)
    stat_affinity: Optional[str] = "Luck"    # "Strength", "Agility", "Magic", "Charisma", "Luck"
    votes: List[str] = field(default_factory=list) # Usernames yang voting pilihan ini
    hp_impact: int = 0                       # Dampak ke darah party (+/-)
    morale_impact: int = 0                   # Dampak ke moral party (+/-)
    gold_impact: int = 0                     # Dampak koin gold
    item_reward: Optional[str] = None        # Item yang didapatkan jika berhasil
    consequence_text: str = ""               # Narasi hasil pilihan

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "dc_check": self.dc_check,
            "stat_affinity": self.stat_affinity,
            "votes": list(self.votes),
            "vote_count": len(self.votes),
            "hp_impact": self.hp_impact,
            "morale_impact": self.morale_impact,
            "gold_impact": self.gold_impact,
            "item_reward": self.item_reward,
            "consequence_text": self.consequence_text
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryChoice":
        clean = {k: v for k, v in data.items() if k != "vote_count"}
        return cls(**clean)


@dataclass
class PartyState:
    name: str = "Guild Chat & Eve"
    hp: int = 100
    max_hp: int = 100
    morale: int = 100
    gold: int = 60
    inventory: List[str] = field(default_factory=lambda: [
        "Pedang Kayu Legendaris",
        "Ramuan HP x2",
        "Obor Abadi",
        "Biskuit Keberuntungan"
    ])
    current_location: str = "Tavern Awal Mula"
    members: List[str] = field(default_factory=lambda: [
        "Eve Maybe (Party Host / Mage)",
        "Creator (Guildmaster)",
        "DiamondHunter (Scout)",
        "Chat Army (Vanguard)"
    ])

    def apply_impact(
        self,
        hp_delta: int = 0,
        morale_delta: int = 0,
        gold_delta: int = 0,
        item_add: Optional[str] = None,
        item_remove: Optional[str] = None
    ):
        self.hp = max(0, min(self.max_hp, self.hp + hp_delta))
        self.morale = max(0, min(100, self.morale + morale_delta))
        self.gold = max(0, self.gold + gold_delta)
        if item_add and item_add not in self.inventory:
            self.inventory.append(item_add)
        if item_remove and item_remove in self.inventory:
            self.inventory.remove(item_remove)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PartyState":
        return cls(**data)


@dataclass
class DiceRollResult:
    roller: str
    d20_value: int                           # 1 to 20
    modifier: int = 0
    total: int = 0
    dc_target: int = 10
    stat_type: str = "Luck"
    is_critical_success: bool = False        # Nat 20
    is_critical_fail: bool = False           # Nat 1
    is_success: bool = False
    outcome_text: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "roller": self.roller,
            "d20_value": self.d20_value,
            "modifier": self.modifier,
            "total": self.total,
            "dc_target": self.dc_target,
            "stat_type": self.stat_type,
            "is_critical_success": self.is_critical_success,
            "is_critical_fail": self.is_critical_fail,
            "is_success": self.is_success,
            "outcome_text": self.outcome_text,
            "timestamp_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiceRollResult":
        clean = {k: v for k, v in data.items() if k != "timestamp_str"}
        return cls(**clean)


@dataclass
class StoryScene:
    id: str
    title: str
    narrative: str
    speaker_name: str
    eve_emotion: str = "happy"               # "excited", "smug", "surprised", "scared", "happy"
    eve_action: str = "wink"                 # "nod", "wink", "tilt", "laugh"
    choices: List[StoryChoice] = field(default_factory=list)
    requires_dice_roll: bool = False
    dc_check: int = 12
    stat_affinity: str = "Agility"
    resolved_choice_id: Optional[str] = None
    dice_result: Optional[DiceRollResult] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "narrative": self.narrative,
            "speaker_name": self.speaker_name,
            "eve_emotion": self.eve_emotion,
            "eve_action": self.eve_action,
            "choices": [c.to_dict() for c in self.choices],
            "requires_dice_roll": self.requires_dice_roll,
            "dc_check": self.dc_check,
            "stat_affinity": self.stat_affinity,
            "resolved_choice_id": self.resolved_choice_id,
            "dice_result": self.dice_result.to_dict() if self.dice_result else None,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryScene":
        choices_raw = data.get("choices", [])
        choices = [StoryChoice.from_dict(c) for c in choices_raw]
        dice_raw = data.get("dice_result")
        dice_res = DiceRollResult.from_dict(dice_raw) if dice_raw else None
        return cls(
            id=data.get("id", f"scene_{uuid.uuid4().hex[:6]}"),
            title=data.get("title", "Adegan Cerita"),
            narrative=data.get("narrative", ""),
            speaker_name=data.get("speaker_name", "Eve Maybe"),
            eve_emotion=data.get("eve_emotion", "happy"),
            eve_action=data.get("eve_action", "wink"),
            choices=choices,
            requires_dice_roll=data.get("requires_dice_roll", False),
            dc_check=data.get("dc_check", 12),
            stat_affinity=data.get("stat_affinity", "Agility"),
            resolved_choice_id=data.get("resolved_choice_id"),
            dice_result=dice_res,
            timestamp=data.get("timestamp", time.time())
        )


@dataclass
class CampaignSession:
    id: str = field(default_factory=lambda: f"campaign_{uuid.uuid4().hex[:6]}")
    title: str = "Petualangan Netherite Terkutuk"
    genre: str = StoryGenre.FANTASY_RPG.value
    eve_role: str = EveRole.DUNGEON_MASTER.value
    status: str = CampaignStatus.IDLE.value
    current_scene: Optional[StoryScene] = None
    scenes_history: List[StoryScene] = field(default_factory=list)
    party: PartyState = field(default_factory=PartyState)
    freeform_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    last_dice_roll: Optional[DiceRollResult] = None
    total_episodes_completed: int = 0
    key_memories: List[str] = field(default_factory=lambda: [
        "Guild Chat pernah mengalahkan Mimic berkat voting lempar biskuit",
        "Eve hampir membakar jenggot kurcaci dengan spell api level 1"
    ])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "eve_role": self.eve_role,
            "status": self.status,
            "current_scene": self.current_scene.to_dict() if self.current_scene else None,
            "scenes_history": [s.to_dict() for s in self.scenes_history],
            "party": self.party.to_dict(),
            "freeform_suggestions": self.freeform_suggestions,
            "last_dice_roll": self.last_dice_roll.to_dict() if self.last_dice_roll else None,
            "total_episodes_completed": self.total_episodes_completed,
            "key_memories": self.key_memories,
            "created_at_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)),
            "updated_at_str": time.strftime("%H:%M:%S", time.localtime(self.updated_at))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CampaignSession":
        cur_sc = StoryScene.from_dict(data["current_scene"]) if data.get("current_scene") else None
        sc_hist = [StoryScene.from_dict(s) for s in data.get("scenes_history", [])]
        party = PartyState.from_dict(data.get("party", {})) if data.get("party") else PartyState()
        last_dice = DiceRollResult.from_dict(data["last_dice_roll"]) if data.get("last_dice_roll") else None

        return cls(
            id=data.get("id", f"campaign_{uuid.uuid4().hex[:6]}"),
            title=data.get("title", "Petualangan Netherite Terkutuk"),
            genre=data.get("genre", StoryGenre.FANTASY_RPG.value),
            eve_role=data.get("eve_role", EveRole.DUNGEON_MASTER.value),
            status=data.get("status", CampaignStatus.IDLE.value),
            current_scene=cur_sc,
            scenes_history=sc_hist,
            party=party,
            freeform_suggestions=data.get("freeform_suggestions", []),
            last_dice_roll=last_dice,
            total_episodes_completed=data.get("total_episodes_completed", 0),
            key_memories=data.get("key_memories", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time())
        )
