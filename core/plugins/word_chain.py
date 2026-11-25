from typing import Any, Dict, List, Optional

from core.plugins.sdk import (
    MaybeAIPlugin,
    PluginContext,
    PluginManifest,
    plugin_command,
)


SEED_WORDS: List[str] = [
    "cyber",
    "bintang",
    "kopi",
    "kucing",
    "lampu",
    "stream",
    "musik",
    "pixel",
]


class WordChainPlugin(MaybeAIPlugin):
    """
    Built-in community chat game plugin: Sambung Kata (Word Chain).
    Supports Indonesian & English words via `!sambungkata` / `!wc`.
    """

    manifest = PluginManifest(
        id="word_chain",
        name="Sambung Kata (Word Chain)",
        version="1.0.0",
        author="MaybeAI",
        description="Game sambung kata interaktif di live chat (Indonesia & English).",
        commands=["!sambungkata", "!wc"],
        events=[],
        creator_only_commands=[],
    )

    def _get_round(self, ctx: PluginContext) -> Dict[str, Any]:
        return ctx.get_plugin_state(
            "round",
            {
                "active": False,
                "current_word": "",
                "used_words": [],
                "scores": {},
                "players": [],
                "seed_idx": 0,
            },
        )

    def _save_round(self, ctx: PluginContext, state: Dict[str, Any]) -> None:
        ctx.set_plugin_state("round", state)

    @staticmethod
    def _format_scores(scores: Dict[str, int]) -> str:
        if not scores:
            return "belum ada skor."
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].lower()))
        return ", ".join(f"{name}: {pts} pts" for name, pts in ranked[:5])

    async def on_load(self, ctx: PluginContext) -> None:
        if ctx.get_plugin_state("round") is None:
            self._save_round(ctx, self._get_round(ctx))

    @plugin_command("!sambungkata", description="Mainkan Sambung Kata di chat")
    @plugin_command("!wc", description="Alias singkat untuk !sambungkata")
    async def handle_word_chain(
        self,
        args: str,
        user: str,
        is_creator: bool,
        ctx: PluginContext,
    ) -> Optional[str]:
        state = self._get_round(ctx)
        raw_args = (args or "").strip()
        parts = raw_args.split()
        sub = parts[0].lower() if parts else "help"

        if sub in ("help", "?"):
            return (
                "Cara main Sambung Kata: ketik `!wc start [kata_awal]` untuk mulai, "
                "`!wc <kata>` untuk menyambung huruf terakhir, `!wc score` untuk papan skor, "
                "atau `!wc stop` untuk mengakhiri ronde!"
            )

        if sub in ("start", "mulai"):
            seed_arg = parts[1].lower() if len(parts) > 1 else ""
            if seed_arg and (not seed_arg.isalpha() or len(seed_arg) < 2):
                return f"@{user} Kata awal harus huruf alfabet minimal 2 karakter ya!"
            if not seed_arg:
                idx = int(state.get("seed_idx", 0)) % len(SEED_WORDS)
                seed_arg = SEED_WORDS[idx]
                state["seed_idx"] = idx + 1

            state["active"] = True
            state["current_word"] = seed_arg
            state["used_words"] = [seed_arg]
            state["scores"] = {}
            state["players"] = [user]
            self._save_round(ctx, state)
            next_char = seed_arg[-1].upper()
            return (
                f"🎮 Ronde Sambung Kata dimulai oleh @{user}! "
                f"Kata pertama: '{seed_arg}'. Ayo lanjutkan dengan huruf '{next_char}'!"
            )

        if sub in ("stop", "end", "selesai"):
            if not state.get("active"):
                return f"@{user} Belum ada ronde Sambung Kata yang aktif. Ketik `!wc start` dulu!"
            summary = self._format_scores(state.get("scores", {}))
            turns = len(state.get("used_words", []))
            state["active"] = False
            self._save_round(ctx, state)
            return f"🏁 Ronde Sambung Kata selesai ({turns} kata)! Klasemen: {summary}"

        if sub in ("score", "scores", "status", "skor"):
            summary = self._format_scores(state.get("scores", {}))
            if not state.get("active"):
                return f"Belum ada ronde aktif. Skor terakhir: {summary}"
            curr = state["current_word"]
            return (
                f"📊 Kata sekarang: '{curr}' (butuh huruf '{curr[-1].upper()}') | "
                f"Kata terpakai: {len(state['used_words'])} | Skor: {summary}"
            )

        if sub == "join":
            if user not in state.get("players", []):
                state.setdefault("players", []).append(user)
                self._save_round(ctx, state)
            if not state.get("active"):
                return f"@{user} sudah siap ikut! Ketik `!wc start` untuk memulai ronde baru."
            curr = state["current_word"]
            return f"@{user} bergabung ke Sambung Kata! Sambung kata '{curr}' dengan huruf '{curr[-1].upper()}'!"

        # Treat sub as a word move
        word = sub
        if len(parts) > 1:
            return f"@{user} Satu kata saja per giliran ya, jangan borong satu kalimat!"
        if not word.isalpha() or len(word) < 2:
            return f"@{user} '{word}' tidak valid — gunakan satu kata alfabet minimal 2 huruf!"

        if not state.get("active"):
            state["active"] = True
            state["current_word"] = word
            state["used_words"] = [word]
            state["scores"] = {user: 1}
            state["players"] = [user]
            self._save_round(ctx, state)
            return (
                f"🎮 Ronde Sambung Kata otomatis dimulai! @{user} membuka dengan '{word}' (+1 pt). "
                f"Giliran berikutnya: huruf '{word[-1].upper()}'!"
            )

        prev_word = state["current_word"]
        expected_letter = prev_word[-1].lower()
        if word[0].lower() != expected_letter:
            return (
                f"Tetot! @{user}, '{word}' tidak dimulai dengan huruf '{expected_letter.upper()}' "
                f"(dari '{prev_word}'). Fokus dong!"
            )

        if word in state["used_words"]:
            return f"@{user} kata '{word}' sudah dipakai sebelumnya! Cari kata baru dong~"

        state["used_words"].append(word)
        state["current_word"] = word
        if user not in state["players"]:
            state["players"].append(user)
        scores = state.setdefault("scores", {})
        scores[user] = int(scores.get(user, 0)) + 1
        self._save_round(ctx, state)

        next_letter = word[-1].upper()
        return (
            f"Nice @{user}! '{word}' nyambung sempurna (+1 pt, total {scores[user]} pts). "
            f"Berikutnya wajib huruf '{next_letter}'!"
        )
