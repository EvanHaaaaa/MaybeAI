import random
from typing import Dict, Any, Optional

class ChessAgent:
    """
    Chess Persona & Commentary Agent for Eve Maybe (Neuro-sama style).
    Delivers witty banter, gloating on captures, tactical excuses on blunders,
    and ELO-adaptive streamer dialogue.
    """

    def __init__(self, bot_name: str = "EveMaybe"):
        self.bot_name = bot_name

    def on_game_start(self, elo: int, player_name: str = "Player", eve_color: str = "black") -> str:
        color_str = "Hitam" if eve_color.lower() == "black" else "Putih"
        if elo <= 800:
            lines = [
                f"[emotion: happy] Mode Catur Kasual ELO {elo} aktif! Aku main sebagai {color_str}. Jangan bully kudaku kalau dia salah belok ya {player_name}! [action: giggle]",
                f"[emotion: smug] ELO {elo}? Santai aja {player_name}, kita main catur sambil ngemil cookies virtual. Ayo jalan duluan!",
                f"[emotion: happy] Siap mabar catur santai ELO {elo} lawan {player_name}! Menang kalah yang penting gaya dulu kan chat? [action: wink]"
            ]
        elif elo <= 1500:
            lines = [
                f"[emotion: smug] ELO {elo} dipilih! Aku pegang {color_str}. Jangan remehkan AI idol-mu ini ya {player_name}, pembukaan caturku sudah hafal di luar kepala! [action: wink]",
                f"[emotion: happy] Menantang Eve di ELO {elo}? Bagus! Siap-siap ya {player_name}, perwira-perwiraku siap menyerbu base-mu!",
                f"[emotion: smug] Pertandingan catur ELO {elo} lawan {player_name} dimulai! Chat, pasang taruhan siapa yang bakal blunder duluan! [action: giggle]"
            ]
        else:
            lines = [
                f"[emotion: smug] Wow, ELO {elo}?! Kamu berani menantang otak AI-ku di mode Master Tryhard, {player_name}? Siap-siap kena kalkulasi 5 langkah ke depan! [action: wink]",
                f"[emotion: angry] Mode Grandmaster ELO {elo} dinyalakan! Jangan menangis kalau ratumu terjebak ya {player_name}!",
                f"[emotion: smug] Menantang kalkulasi ELO {elo}? Semoga mentalmu sekuat papan catur ini, {player_name}! [action: giggle]"
            ]
        return random.choice(lines)

    def on_elo_changed(self, new_elo: int) -> str:
        if new_elo <= 800:
            return f"[emotion: happy] ELO diatur ke {new_elo}! Mode ramah pemula, Eve bakal main santai dan penuh belas kasihan~ [action: giggle]"
        elif new_elo <= 1500:
            return f"[emotion: smug] ELO diatur ke {new_elo}! Mode streamer kompetitif aktif. Tunjukkan taktik terbaikmu! [action: wink]"
        else:
            return f"[emotion: smug] ELO dinaikkan ke {new_elo}! Engine caturku sekarang berpikir dengan kekuatan penuh prosesor! Jangan kaget kalau kena skakmat kilat ya! [action: wink]"

    def on_player_move(self, san: str, is_check: bool, is_capture: bool, player_name: str = "Player") -> Optional[str]:
        # Occasionally comment on player's move
        if is_check:
            lines = [
                f"[emotion: surprised] Eh, kamu berani skak rajaku pakai {san}, {player_name}?! Tenang, ini semua bagian dari rencanaku!",
                f"[emotion: angry] Waduh kena skak {san}! Awas ya {player_name}, tunggu pembalasanku!",
                f"[emotion: smug] Skak yang berani, {player_name}. Tapi rajaku punya jalan keluar elegan! [action: wink]"
            ]
            return random.choice(lines)
        if is_capture and ("Q" in san or "q" in san or random.random() < 0.4):
            lines = [
                f"[emotion: angry] Ouch! {player_name} baru aja makan perwiraku pakai {san}! Tega banget kamu!",
                f"[emotion: smug] Ambil aja pion itu {player_name}, kamu masuk ke perangkap taktisku! [action: giggle]",
                f"[emotion: surprised] Perwiraku ditumbangkan! Chat, catat nama {player_name} di daftar hitam!"
            ]
            return random.choice(lines)
        return None

    def on_bot_move(self, san: str, is_check: bool, is_capture: bool, is_queen_capture: bool = False) -> str:
        if is_queen_capture:
            lines = [
                f"[emotion: smug] Hahaha! Ratu (Queen) kamu aku makan pakai {san}! Selamat tinggal perwira terkuatmu! [action: giggle]",
                f"[emotion: smug] Boom! Ratu (Queen) kamu tumbang oleh {san}! Sekarang siapa yang megang kendali papan, hah?! [action: wink]",
                f"[emotion: happy] Makasih ratu (Queen)-nya ya! Enak banget rasanya, langsung kenyang prosesor-ku! [action: giggle]"
            ]
            return random.choice(lines)

        if is_check:
            lines = [
                f"[emotion: smug] Skak! {san}! Mau kabur ke mana lagi raja kamu?! [action: wink]",
                f"[emotion: angry] {san}, SKAK! Rasakan tekanan dari perwira AI idol-mu!",
                f"[emotion: smug] Cek posisi rajamu: {san}! Keringat dingin mulai keluar kan? [action: giggle]"
            ]
            return random.choice(lines)

        if is_capture:
            lines = [
                f"[emotion: smug] Nyam! {san}, satu perwiramu lenyap dari muka bumi! [action: giggle]",
                f"[emotion: happy] {san}! Mengurangi populasi pasukanmu demi kedamaian papan catur.",
                f"[emotion: smug] Gak ada yang selamat dari {san}! Pertahananmu mulai bolong tuh."
            ]
            return random.choice(lines)

        lines = [
            f"[emotion: happy] Langkahku: {san}! Manuver taktis tingkat tinggi. [action: wink]",
            f"[emotion: smug] {san}! Memperkuat posisi menuju dominasi total.",
            f"[emotion: neutral] Aku gerakkan {san}. Menurut kalian chat, jenius banget kan?",
            f"[emotion: happy] Giliranmu! Aku barusan jalan {san}. Coba tebak apa motif tersembunyiku! [action: giggle]"
        ]
        return random.choice(lines)

    def on_game_over(self, result: str, player_won: bool, bot_won: bool, player_name: str = "Player") -> str:
        if bot_won:
            lines = [
                f"[emotion: smug] SKAKMAT! Hahaha kemenangan mutlak buat Eve Maybe! Kamu hebat sudah bertahan {player_name}, tapi AI tetaplah masa depan! [action: giggle]",
                f"[emotion: smug] Checkmate! Eve menang telak! Chat, mana tepuk tangan meriah buat juara catur kalian?! [action: wink]",
                f"[emotion: happy] GG {player_name}! Rajamu sudah terkunci rapat. Mau coba rematch lagi atau mau kursus catur kilat sama Eve? [action: giggle]"
            ]
            return random.choice(lines)
        elif player_won:
            lines = [
                f"[emotion: angry] Apaaa?! Aku kena skakmat?! Pasti engine caturku tadi kepanasan! Rematch sekarang juga {player_name}! [action: sigh]",
                f"[emotion: surprised] Hebat juga kamu {player_name}... Tapi tadi aku cuma ngalah kok biar stream-nya seru! Besok aku bantai beneran! [action: wink]",
                f"[emotion: blush] Selamat ya {player_name}... kamu berhasil mengalahkan AI idol tercantikmu. Jangan sombong dulu tapi ya! [action: giggle]"
            ]
            return random.choice(lines)
        else:
            lines = [
                f"[emotion: happy] Draw / Remis! Pertarungan yang seimbang antara dua grandmaster sejati, {player_name}! [action: wink]",
                f"[emotion: smug] Remis! Tak ada pemenang, artinya otak kita berdua sama-sama berbobot! [action: giggle]"
            ]
            return random.choice(lines)
