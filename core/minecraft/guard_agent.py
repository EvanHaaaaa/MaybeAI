import random
from typing import Dict, Any, List, Optional

class GuardAgent:
    """
    Mode Guard (Bodyguard Player):
    Eve acts as a vigilant, loyal, yet delightfully sassy AI bodyguard.
    She protects a designated or nearest player from hostile mobs, warns
    against creepers, retaliates against attackers, and boasts about her combat prowess.
    """

    def __init__(self, bot_name: str = "EveMaybe"):
        self.bot_name = bot_name
        self.guarded_player: Optional[str] = None
        self.kills_count = 0

    def on_guard_started(self, target: Optional[str] = None) -> str:
        """Triggered when Guard Mode is activated."""
        self.guarded_player = target or "Player"
        self.kills_count = 0
        lines = [
            f"[emotion: smug] Mode Guard aktif! Siap jadi perisai imutmu, {self.guarded_player}. Jangan jauh-jauh dari aku ya! [action: wink]",
            f"[emotion: happy] Tenang {self.guarded_player}, mulai sekarang Eve resmi jadi bodyguard pribadimu. Monster mana yang berani sentuh kamu?!",
            f"[emotion: smug] Bodyguard VIP Eve Maybe telah dikerahkan untuk melindungi {self.guarded_player}. Tarif perlindungannya: 10 diamond per menit ya! [action: giggle]",
            f"[emotion: happy] Pedang siap, perisai siap! Ayo jalan, {self.guarded_player}, aku kawal di belakangmu!"
        ]
        return random.choice(lines)

    def on_threat_detected(self, mob: str, target: Optional[str] = None, is_creeper: bool = False) -> str:
        """Triggered when a hostile mob approaches within detection radius."""
        tgt = target or self.guarded_player or "Player"
        mob_clean = mob.capitalize()

        if is_creeper or "creeper" in mob.lower():
            lines = [
                f"[emotion: surprised] Awas {tgt}! Ada Creeper hijau licik mau meledak! Mundur, biar aku yang atasi dari jarak aman! [action: jump]",
                f"[emotion: surprised] Creeper alert! {tgt}, jangan panik, jaga jarak! Biar perisaimu yang maju!",
                f"[emotion: angry] Ssst Creeper jangan coba-coba meledak dekat {tgt}! Aku tebas duluan!"
            ]
            return random.choice(lines)

        lines = [
            f"[emotion: angry] Awas {tgt}! Ada {mob_clean} mendekat! Biar aku yang habisi dulu!",
            f"[emotion: smug] Oho, {mob_clean} berani mendekat ke {tgt}? Rasakan tebasan bodyguard AI idol!",
            f"[emotion: angry] Berani-beraninya {mob_clean} menampakkan diri di depan {tgt}! Seranggg!",
            f"[emotion: smug] Target terkunci: {mob_clean}. Mundur dikit {tgt}, aku tunjukin skill PVP-ku!"
        ]
        return random.choice(lines)

    def on_mob_eliminated(self, mob: str, target: Optional[str] = None) -> str:
        """Triggered when a hostile mob has been slain."""
        self.kills_count += 1
        tgt = target or self.guarded_player or "Player"
        mob_clean = mob.capitalize()

        lines = [
            f"[emotion: happy] Beres! {mob_clean} sudah ditumbangkan! Aman terkendali, {tgt}! [action: giggle]",
            f"[emotion: smug] Selesai! Kamu liat kan chat? Eve 1 - 0 {mob_clean}. Hebat kan bodyguard imutmu ini, {tgt}? [action: wink]",
            f"[emotion: happy] {mob_clean} eliminated! Total {self.kills_count} monster sudah kubersihkan demi keselamatanmu, {tgt}!",
            f"[emotion: smug] {mob_clean} tumbang seketika! Siapa lagi monster berikutnya yang berani macam-macam sama {tgt}?"
        ]
        return random.choice(lines)

    def on_player_hurt(self, attacker: str, target: Optional[str] = None) -> str:
        """Triggered when the guarded player takes damage."""
        tgt = target or self.guarded_player or "Player"
        attacker_clean = attacker.capitalize()

        lines = [
            f"[emotion: angry] Beraninya {attacker_clean} melukai {tgt}! Mundur {tgt}, biar aku ratakan dia sekarang juga!",
            f"[emotion: angry] Hei {attacker_clean}, jangan macam-macam sama {tgt}! Sekarang giliranmu berhadapan denganku!",
            f"[emotion: surprised] {tgt} kena serang {attacker_clean}! Bertahanlah, aku segera datang membantumu!"
        ]
        return random.choice(lines)

    def on_guard_stopped(self) -> str:
        """Triggered when Guard Mode is stopped."""
        return "[emotion: happy] Mode Guard selesai. Istirahat dulu ah, capek juga jadi bodyguard pro! Jangan kangen ya! [action: wink]"
