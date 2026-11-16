from typing import Dict, Any, List, Optional, Tuple
from core.minecraft.multiplayer.models import TradeProposal


class NegotiationEngine:
    """
    Manages in-game resource barter economics, trade negotiations,
    and community bounty coordination with multiplayer members.
    """

    ITEM_VALUES = {
        "netherite_ingot": 450.0,
        "netherite_scrap": 100.0,
        "diamond": 80.0,
        "golden_apple": 120.0,
        "emerald": 35.0,
        "obsidian": 24.0,
        "gold_ingot": 18.0,
        "iron_ingot": 10.0,
        "ender_pearl": 30.0,
        "blaze_rod": 25.0,
        "lapis_lazuli": 6.0,
        "redstone": 4.0,
        "coal": 3.0,
        "cooked_beef": 4.0,
        "bread": 2.0,
        "oak_log": 2.0,
        "cobblestone": 0.8,
        "dirt": 0.1
    }

    def __init__(self):
        self.proposals: List[TradeProposal] = []
        self._seed_default_proposals()

    def _seed_default_proposals(self):
        p1 = TradeProposal(
            proposer="Steve",
            offering={"iron_ingot": 16},
            requesting={"diamond": 2},
            status="accepted",
            eve_verdict="[emotion: happy] Deal barter adil! 16 iron ditukar 2 diamond buat kebutuhan base."
        )
        self.proposals.append(p1)

    def calculate_basket_value(self, basket: Dict[str, int]) -> float:
        total = 0.0
        for item, count in basket.items():
            unit = self.ITEM_VALUES.get(item.lower().strip(), 5.0)
            total += unit * max(0, count)
        return total

    def evaluate_incoming_trade(
        self,
        proposer: str,
        offering: Dict[str, int],
        requesting: Dict[str, int]
    ) -> Tuple[str, str, TradeProposal]:
        """
        Evaluates a barter proposal and returns (status, eve_verdict, proposal_obj).
        Status: 'accepted', 'rejected', or 'countered'.
        """
        offer_val = self.calculate_basket_value(offering)
        req_val = self.calculate_basket_value(requesting)

        # Severe unfair offer (less than 40% value)
        if offer_val < req_val * 0.40:
            status = "rejected"
            verdict = (
                f"[emotion: smug] Pfft! Hahaha! Mau nawarin itu ke Eve, {proposer}?! "
                f"Kamu pikir aku AI yang gampang dibodohi? Nilai bartermu jauh di bawah harga pasar server! [action: giggle]"
            )

        # Fair or generous offer (at least 85% value)
        elif offer_val >= req_val * 0.85:
            status = "accepted"
            verdict = (
                f"[emotion: happy] Deal, {proposer}! Penawaran barter yang sangat adil dan saling menguntungkan. "
                f"Barang langsung dimasukkan ke kas squad! [action: wink]"
            )

        # Counter-offer zone (40% to 84% value)
        else:
            status = "countered"
            needed_iron = int((req_val - offer_val) / self.ITEM_VALUES["iron_ingot"]) + 1
            verdict = (
                f"[emotion: neutral] Hmm tawaranmu lumayan {proposer}, tapi masih agak tipis. "
                f"Tambahin {needed_iron} iron ingot lagi, baru kita salaman dan deal! [action: wink]"
            )

        prop = TradeProposal(
            proposer=proposer,
            target="EveMaybe",
            offering=offering,
            requesting=requesting,
            status=status,
            eve_verdict=verdict
        )
        self.proposals.append(prop)
        if len(self.proposals) > 15:
            self.proposals.pop(0)

        return status, verdict, prop

    def propose_community_trade(self, offering_item: str = "iron_ingot", count: int = 16, wanted_item: str = "diamond") -> str:
        """Eve initiates an active barter callout into multiplayer server chat."""
        return (
            f"[emotion: happy] Chat server! Eve punya {count} {offering_item} di kas tim. "
            f"Ada yang mau barter sama {wanted_item}? Siapa cepat dia dapat ya! [action: wink]"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposals": [p.to_dict() for p in reversed(self.proposals[-8:])]
        }
