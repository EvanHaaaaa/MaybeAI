import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from core.planning.models import (
    Goal,
    GoalCategory,
    GoalStatus,
    ReflectionLesson,
    Subtask,
    parse_reflection_lesson,
)


MAX_REPLAN_ATTEMPTS = 3
MAX_STORED_LESSONS = 50


# Candidate strategies per (category, root_cause) so repeated failures pivot to distinct plans.
_STRATEGY_CATALOG: Dict[Tuple[str, str], List[Dict[str, str]]] = {
    (GoalCategory.MINECRAFT.value, "hostile_mob_ambush"): [
        {
            "id": "mc_shield_strip_mine",
            "title": "[Plan B] Buat Shield & Gali Terowongan Tambang Aman (Y=16)",
            "strategy": "Buat Shield (Perisai) & gali Strip Mine tangga aman di Y=16 dengan penerangan penuh.",
            "speech": "[emotion: angry] Hadeh! Rencana awal gagal gara-gara {reason}! Tapi santai chat, AI jenius ini selalu punya Plan B: kita bikin perisai dulu dan gali terowongan aman di bawah tanah! [action: sigh]",
        },
        {
            "id": "mc_barricade_daylight",
            "title": "[Plan B] Barikade Area & Kumpulkan Sumber Daya Siang Hari",
            "strategy": "Tutup akses mob dengan blok pelindung, pasang obor keliling, dan kumpulkan resource saat siang hari.",
            "speech": "[emotion: smug] Terowongan tadi masih terlalu bahaya! Plan B berikutnya: kita pasang barikade dan penerangan penuh dulu sebelum lanjut! [action: wink]",
        },
        {
            "id": "mc_villager_trade_safe",
            "title": "[Plan B] Alihkan ke Rute Aman & Barter Desa",
            "strategy": "Hindari zona mob berbahaya dan kumpulkan kebutuhan lewat rute permukaan aman atau barter villager.",
            "speech": "[emotion: neutral] Oke, zona ini terlalu brutal. Saatnya strategi defensif total lewat rute permukaan yang aman! [action: nod]",
        },
    ],
    (GoalCategory.MINECRAFT.value, "resource_depletion"): [
        {
            "id": "mc_explore_new_biome",
            "title": "[Plan B] Eksplorasi Biome Baru / Cari Sumber Daya Sekunder",
            "strategy": "Eksplorasi wilayah tebing seberang atau bongkar kayu dari reruntuhan desa terdekat.",
            "speech": "[emotion: smug] Waduh area sini zonk banget! Jangan panik chat, kita ubah haluan: jalan ke koordinat seberang buat cari pasokan baru. Fleksibilitas adalah kunci kesuksesan AI! [action: wink]",
        },
        {
            "id": "mc_deep_branch_mine",
            "title": "[Plan B] Gali Branch Mine Sistematis di Koordinat Baru",
            "strategy": "Pindah ke koordinat baru dan lakukan branch mining berjarak 2 blok untuk memaksimalkan temuan.",
            "speech": "[emotion: neutral] Area permukaan tetap kosong, jadi kita pindah koordinat dan gali branch mine sistematis! [action: wink]",
        },
        {
            "id": "mc_recycle_craft_alt",
            "title": "[Plan B] Gunakan Material Alternatif & Craft Ulang",
            "strategy": "Substitusi material yang langka dengan bahan alternatif terdekat atau daur ulang stok inventori.",
            "speech": "[emotion: happy] Kalau bahan utama gak ketemu, kita improvisasi pakai material alternatif yang tersedia! [action: giggle]",
        },
    ],
    (GoalCategory.MINECRAFT.value, "connection_blocked"): [
        {
            "id": "mc_verify_connection_retry",
            "title": "[Plan B] Periksa Koneksi Bot & Sinkronisasi Telemetry",
            "strategy": "Verifikasi status koneksi Minecraft bot sebelum mengirim aksi ulang.",
            "speech": "[emotion: sad] Koneksi ke server Minecraft sempat terputus ({reason}). Kita cek ulang koneksi dan sinkronisasi dulu ya! [action: sigh]",
        },
        {
            "id": "mc_fallback_safe_idle",
            "title": "[Plan B] Tunda Aksi Berat & Jalankan Tugas Persiapan Lokal",
            "strategy": "Alihkan sementara ke langkah persiapan non-fisik sampai koneksi server pulih.",
            "speech": "[emotion: neutral] Server masih belum merespons, jadi kita siapkan rencana lokal dulu! [action: nod]",
        },
    ],
    (GoalCategory.SOCIAL.value, "audience_unresponsive"): [
        {
            "id": "soc_active_chatter_pivot",
            "title": "[Plan B] Ajak Ngobrol Chatter Aktif Lain & Lempar Topik Lucu",
            "strategy": "Beralih menyapa chatter lain yang aktif dan buat candaan tentang penolakan barusan.",
            "speech": "[emotion: smug] Dikacangin? Santai, AI idol kalian ini mentalnya baja tahan karat! Masih banyak manusia ramah lainnya di chat yang mau temenan sama aku kok! [action: giggle]",
            "unit": "interaction",
        },
        {
            "id": "soc_interactive_poll",
            "title": "[Plan B] Lempar Mini-Quiz & Pertanyaan Terbuka ke Chat",
            "strategy": "Ganti sapaan satu-satu dengan pertanyaan pilihan ganda atau mini-quiz untuk memancing respons massal.",
            "speech": "[emotion: happy] Oke, sapaan personal belum dibalas — waktunya lempar mini-quiz seru buat seluruh chat! [action: wink]",
            "unit": "interaction",
        },
        {
            "id": "soc_storytelling_hook",
            "title": "[Plan B] Mulai Cerita Singkat & Minta Pendapat Penonton",
            "strategy": "Bagikan anekdot singkat yang relatable lalu minta chat memberi rating atau komentar.",
            "speech": "[emotion: excited] Biar suasana cair, aku ceritain kejadian lucu dulu deh — kalian wajib kasih skor 1-10 ya! [action: giggle]",
            "unit": "interaction",
        },
    ],
    (GoalCategory.CHESS.value, "tactical_blunder"): [
        {
            "id": "chess_solid_defense",
            "title": "[Plan B] Reset Strategi: Terapkan Pertahanan Solid & Balas Dendam",
            "strategy": "Gunakan formasi pertahanan solid (Caro-Kann / London System) dan prioritaskan keamanan Raja.",
            "speech": "[emotion: smug] Tadi itu cuma uji coba software ya chat, bukan blunder betulan! Sekarang mode balas dendam aktif: aku pakai taktik pertahanan benteng yang gak bakal bisa ditembus! [action: pout]",
        },
        {
            "id": "chess_piece_trade_endgame",
            "title": "[Plan B] Sederhanakan Papan & Tukar Perwira Menuju Endgame",
            "strategy": "Kurangi kompleksitas taktis dengan pertukaran perwira seimbang dan fokus pada struktur pion endgame.",
            "speech": "[emotion: neutral] Taktik agresif tadi berisiko. Sekarang kita sederhanakan papan dan main rapi ke endgame! [action: nod]",
        },
        {
            "id": "chess_center_control_slow",
            "title": "[Plan B] Kontrol Petak Tengah Bertahap & Rokade Cepat",
            "strategy": "Prioritaskan perkembangan perwira minor, rokade dini, dan hindari serangan prematur.",
            "speech": "[emotion: happy] Saatnya main sabar: amankan raja dulu, kuasai tengah papan pelan-pelan! [action: wink]",
        },
    ],
    (GoalCategory.PERFORMANCE.value, "audio_or_stage_error"): [
        {
            "id": "perf_acoustic_fallback",
            "title": "[Plan B] Ganti ke Lagu Akustik / Tempo Santai",
            "strategy": "Alihkan setlist ke lagu tempo santai dengan aransemen ringan untuk menjaga kualitas panggung.",
            "speech": "[emotion: smug] Ada kendala teknis di panggung ({reason}), tapi show must go on! Plan B: kita ganti ke setlist akustik yang lebih stabil! [action: wink]",
        },
        {
            "id": "perf_crowd_mc_bridge",
            "title": "[Plan B] Sisipkan Segmen MC Interaktif Sebelum Lagu Berikutnya",
            "strategy": "Jembatani kendala audio dengan segmen MC interaktif bersama chat sambil reset audio.",
            "speech": "[emotion: happy] Plan B aktif! Sambil nunggu panggung siap lagi, kita ngobrol & nyalakan glowstick bareng dulu yuk! [action: giggle]",
        },
    ],
}


class StrategyReplanner:
    """
    Handles dynamic strategy adaptation when a subtask or plan encounters failure.
    Supports causal failure diagnosis, strategy success-rate scoring, and bounded
    reflection lesson learning (gated by `use_causal_reflection`).
    """

    MAX_REPLAN_ATTEMPTS = MAX_REPLAN_ATTEMPTS
    use_causal_reflection: bool = True

    _strategy_stats: Dict[str, Dict[str, Any]] = {}
    _recent_lessons: List[ReflectionLesson] = []

    @classmethod
    def reset_learning_state(cls) -> None:
        """Clears in-memory strategy statistics and reflection lesson history (useful for tests)."""
        cls._strategy_stats.clear()
        cls._recent_lessons.clear()

    @classmethod
    def set_use_causal_reflection(cls, enabled: bool) -> None:
        cls.use_causal_reflection = bool(enabled)

    @classmethod
    def _strategy_key(cls, strategy: str, category: str = "general") -> str:
        norm_cat = (category or "general").strip().lower()
        norm_strat = " ".join((strategy or "").strip().lower().split())
        return f"{norm_cat}::{norm_strat}"

    @classmethod
    def record_strategy_outcome(
        cls,
        strategy: str,
        success: bool,
        category: str = "general",
        failure_reason: str = "",
    ) -> Dict[str, Any]:
        """Records whether a strategy succeeded or failed and updates its running stats."""
        strat_name = (strategy or "").strip() or "default_strategy"
        key = cls._strategy_key(strat_name, category)
        entry = cls._strategy_stats.setdefault(
            key,
            {
                "strategy": strat_name,
                "category": (category or "general").strip().lower(),
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_failure_reason": "",
                "last_updated": time.time(),
            },
        )
        entry["attempts"] += 1
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1
            if failure_reason:
                entry["last_failure_reason"] = failure_reason
        entry["last_updated"] = time.time()
        entry["success_rate"] = cls.get_strategy_success_rate(strat_name, category)
        return dict(entry)

    @classmethod
    def get_strategy_success_rate(
        cls,
        strategy: str,
        category: str = "general",
        prior_success: float = 0.5,
        prior_weight: float = 2.0,
    ) -> float:
        """Computes Bayesian-smoothed success rate in [0.0, 1.0] for a strategy."""
        key = cls._strategy_key(strategy, category)
        entry = cls._strategy_stats.get(key)
        if not entry:
            return prior_success
        attempts = float(entry["attempts"])
        successes = float(entry["successes"])
        return round((successes + prior_success * prior_weight) / (attempts + prior_weight), 4)

    @classmethod
    def record_reflection_lesson(cls, lesson: ReflectionLesson) -> None:
        """Stores a structured reflection lesson in the bounded history."""
        if not lesson:
            return
        cls._recent_lessons.append(lesson)
        if len(cls._recent_lessons) > MAX_STORED_LESSONS:
            cls._recent_lessons = cls._recent_lessons[-MAX_STORED_LESSONS:]

    @classmethod
    def get_recent_lessons(
        cls,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[ReflectionLesson]:
        """Returns up to `limit` most recent lessons, optionally filtered by category."""
        cap = max(1, int(limit))
        lessons = cls._recent_lessons
        if category:
            norm_cat = category.strip().lower()
            filtered = [l for l in lessons if (l.category or "").lower() == norm_cat]
            if filtered:
                return list(filtered[-cap:])
        return list(lessons[-cap:])

    @classmethod
    def sync_goal_reflections(cls, goals: List[Goal], limit: int = 5) -> List[ReflectionLesson]:
        """Extracts recent lessons from Goal history and ensures they are indexed for replanning."""
        collected: List[ReflectionLesson] = []
        for g in goals or []:
            for lesson in g.get_recent_lessons(limit=limit):
                collected.append(lesson)
        return collected[-max(1, int(limit)):]

    @classmethod
    def _infer_category(cls, goal: Optional[Goal], subtask: Subtask, failure_reason: str) -> str:
        cat = (subtask.category or (goal.category if goal else "") or "").strip().lower()
        if cat and cat != GoalCategory.GENERAL.value:
            return cat
        combined = f"{goal.title if goal else ''} {subtask.title} {subtask.description} {failure_reason}".lower()
        if any(w in combined for w in ["creeper", "mob", "zombie", "skeleton", "iron", "mine", "kayu", "oak", "biome", "minecraft", "speedrun"]):
            return GoalCategory.MINECRAFT.value
        if any(w in combined for w in ["catur", "chess", "blunder", "skakmat", "menteri", "queen", "elo"]):
            return GoalCategory.CHESS.value
        if any(w in combined for w in ["kacang", "chatter", "player", "sosial", "social", "chat", "penonton"]):
            return GoalCategory.SOCIAL.value
        if any(w in combined for w in ["konser", "karaoke", "lagu", "song", "glowstick", "stage", "performance"]):
            return GoalCategory.PERFORMANCE.value
        return cat or GoalCategory.GENERAL.value

    @classmethod
    def _infer_root_cause(cls, failure_reason: str, category: str) -> str:
        reason_lower = (failure_reason or "").lower()
        if any(w in reason_lower for w in ["creeper", "mati", "death", "mob", "zombie", "skeleton", "diserang", "spider", "lava"]):
            return "hostile_mob_ambush"
        if any(w in reason_lower for w in ["habis", "kosong", "tidak ada", "jauh", "out of resource", "not found", "no real inventory delta"]):
            return "resource_depletion"
        if any(w in reason_lower for w in ["not connected", "disconnected", "blocked", "timeout", "offline server"]):
            return "connection_blocked"
        if any(w in reason_lower for w in ["kacang", "ignore", "offline", "left", "menolak", "silent", "no reply"]):
            return "audience_unresponsive"
        if any(w in reason_lower for w in ["blunder", "kalah", "skakmat", "menteri", "queen lost", "defeat", "checkmate"]):
            return "tactical_blunder"
        if category == GoalCategory.PERFORMANCE.value or any(w in reason_lower for w in ["audio", "mic", "tts", "song", "karaoke", "stage", "glowstick"]):
            return "audio_or_stage_error"
        return "general_execution_failure"

    @classmethod
    def _collect_lessons(
        cls,
        goal: Optional[Goal],
        reflections: Optional[List[Any]],
        category: str,
        limit: int = 5,
    ) -> List[ReflectionLesson]:
        lessons: List[ReflectionLesson] = []
        if goal is not None:
            lessons.extend(goal.get_recent_lessons(limit=limit))
        if reflections:
            for item in reflections:
                parsed = parse_reflection_lesson(item)
                if parsed is not None:
                    lessons.append(parsed)
        else:
            lessons.extend(cls.get_recent_lessons(category=category, limit=limit))
        return lessons[-max(1, int(limit)):]

    @classmethod
    def diagnose_failure(
        cls,
        failed_subtask: Subtask,
        failure_reason: str,
        goal: Optional[Goal] = None,
        reflections: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Performs causal diagnosis of a subtask failure using history and stored reflections."""
        category = cls._infer_category(goal, failed_subtask, failure_reason)
        root_cause = cls._infer_root_cause(failure_reason, category)
        lessons = cls._collect_lessons(goal, reflections, category=category, limit=5)

        failed_strategies: List[str] = []
        if failed_subtask.strategy:
            failed_strategies.append(failed_subtask.strategy)
        if failed_subtask.alternative_strategy and failed_subtask.alternative_strategy not in failed_strategies:
            failed_strategies.append(failed_subtask.alternative_strategy)

        if goal is not None:
            for sub in goal.subtasks:
                if sub.status in (GoalStatus.REPLANNED.value, GoalStatus.FAILED.value) and sub.strategy:
                    if sub.strategy not in failed_strategies:
                        failed_strategies.append(sub.strategy)

        matching_lessons: List[ReflectionLesson] = []
        for lesson in lessons:
            if lesson.root_cause == root_cause or lesson.category == category or lesson.strategy_used in failed_strategies:
                matching_lessons.append(lesson)
                if lesson.strategy_used and lesson.strategy_used not in failed_strategies:
                    failed_strategies.append(lesson.strategy_used)

        return {
            "category": category,
            "root_cause": root_cause,
            "failed_strategy": failed_subtask.strategy or failed_subtask.title,
            "failed_strategies": failed_strategies,
            "matching_lessons": matching_lessons,
            "is_repeated_failure": len(matching_lessons) > 0 or failed_subtask.attempts > 1,
        }

    @classmethod
    def _build_general_candidates(
        cls,
        failed_subtask: Subtask,
        failure_reason: str,
        category: str,
    ) -> List[Dict[str, str]]:
        base_title = failed_subtask.title[:35]
        return [
            {
                "id": f"{category}_alt_1",
                "title": f"[Plan B] {base_title} (Alternatif)",
                "strategy": f"Penyesuaian taktik alternatif: modifikasi pendekatan untuk mengatasi {failure_reason}.",
                "speech": f"[emotion: neutral] Rencana lama terhambat karena '{{reason}}'. Tenang, sistem kalkulasiku sudah memperbarui rute: kita lanjutkan dengan strategi Plan B sekarang! [action: wink]",
            },
            {
                "id": f"{category}_alt_2",
                "title": f"[Plan B-2] {base_title} (Pecah Langkah Kecil)",
                "strategy": f"Pecah target menjadi langkah inkremental kecil dan verifikasi kondisi sebelum eksekusi ({failure_reason}).",
                "speech": f"[emotion: smug] Plan B pertama masih menemui hambatan ({failure_reason}). Sekarang kita pecah jadi langkah kecil yang lebih aman! [action: nod]",
            },
            {
                "id": f"{category}_alt_3",
                "title": f"[Plan B-3] {base_title} (Pendekatan Konservatif)",
                "strategy": f"Gunakan mode konservatif berisiko rendah dan validasi prasyarat sebelum mencoba ulang ({failure_reason}).",
                "speech": f"[emotion: neutral] Oke, kita aktifkan pendekatan konservatif berisiko rendah biar progres tetap jalan! [action: wink]",
            },
        ]

    @classmethod
    def select_best_strategy(
        cls,
        category: str,
        root_cause: str = "",
        failed_strategies: Optional[List[str]] = None,
        candidates: Optional[List[Dict[str, Any]]] = None,
        reflections: Optional[List[Any]] = None,
        failed_subtask: Optional[Subtask] = None,
        failure_reason: str = "",
    ) -> Dict[str, Any]:
        """Scores candidate strategies by success rate, causal fit, and prior failure avoidance."""
        norm_cat = (category or GoalCategory.GENERAL.value).strip().lower()
        norm_cause = (root_cause or "general_execution_failure").strip().lower()
        excluded = {s.strip().lower() for s in (failed_strategies or []) if s and s.strip()}

        parsed_lessons: List[ReflectionLesson] = []
        for item in (reflections or []):
            parsed = parse_reflection_lesson(item)
            if parsed is not None:
                parsed_lessons.append(parsed)
                if parsed.strategy_used and parsed.outcome == "failed":
                    excluded.add(parsed.strategy_used.strip().lower())

        pool = list(candidates) if candidates else list(_STRATEGY_CATALOG.get((norm_cat, norm_cause), []))
        if not pool:
            # Fallback to any catalog entries for this category or general candidates
            for (cat_key, _), entries in _STRATEGY_CATALOG.items():
                if cat_key == norm_cat and norm_cause == "general_execution_failure":
                    pool.extend(entries)
            if not pool:
                dummy_sub = failed_subtask or Subtask(id="sub_tmp", title="Misi", category=norm_cat)
                pool = cls._build_general_candidates(dummy_sub, failure_reason or norm_cause, norm_cat)

        recommended_boosts = {
            l.recommended_alternative.strip().lower()
            for l in parsed_lessons
            if l.recommended_alternative and l.recommended_alternative.strip().lower() not in excluded
        }

        scored: List[Tuple[float, int, Dict[str, Any]]] = []
        for idx, cand in enumerate(pool):
            strat_text = str(cand.get("strategy", "")).strip()
            strat_norm = strat_text.lower()
            base_rate = cls.get_strategy_success_rate(strat_text, norm_cat)
            score = base_rate

            if strat_norm in excluded or any(ex and ex in strat_norm for ex in excluded):
                score -= 2.0
            if strat_norm in recommended_boosts:
                score += 0.25

            # Deterministic tie-breaker: preserve catalog order when scores are equal
            scored.append((score, -idx, cand))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, _, best_cand = scored[0]
        result = dict(best_cand)
        result["score"] = round(best_score, 4)
        return result

    @classmethod
    def replan_subtask(
        cls,
        goal: Goal,
        failed_subtask: Subtask,
        failure_reason: str,
        reflections: Optional[List[Any]] = None,
        use_causal_reflection: Optional[bool] = None,
    ) -> Tuple[Optional[Subtask], str]:
        """
        Adapts the plan by diagnosing the failure, selecting the highest-scoring distinct
        alternative strategy, recording a structured reflection lesson, and returning
        (new_subtask, speech_commentary).
        Falls back to keyword-only replanning when `use_causal_reflection` is False.
        """
        causal_enabled = cls.use_causal_reflection if use_causal_reflection is None else bool(use_causal_reflection)
        if not causal_enabled:
            return cls._keyword_replan_subtask(goal, failed_subtask, failure_reason)

        diagnosis = cls.diagnose_failure(
            failed_subtask=failed_subtask,
            failure_reason=failure_reason,
            goal=goal,
            reflections=reflections,
        )
        category = diagnosis["category"]
        root_cause = diagnosis["root_cause"]
        failed_strategy = diagnosis["failed_strategy"]

        cls.record_strategy_outcome(
            strategy=failed_strategy,
            success=False,
            category=category,
            failure_reason=failure_reason,
        )

        if failed_subtask.attempts >= MAX_REPLAN_ATTEMPTS:
            failed_subtask.mark_failed(failure_reason)
            goal.recalculate_progress()
            goal.status = GoalStatus.FAILED.value
            chosen_alt = cls.select_best_strategy(
                category=category,
                root_cause=root_cause,
                failed_strategies=diagnosis["failed_strategies"],
                reflections=diagnosis["matching_lessons"],
                failed_subtask=failed_subtask,
                failure_reason=failure_reason,
            )
            lesson = goal.add_reflection_lesson(
                strategy_used=failed_strategy,
                failure_reason=failure_reason,
                root_cause=root_cause,
                recommended_alternative=chosen_alt["strategy"],
                category=category,
                subtask_title=failed_subtask.title,
                outcome="failed",
            )
            cls.record_reflection_lesson(lesson)
            speech = (
                f"[emotion: sad] Aduh chat, rencana untuk '{failed_subtask.title}' gagal terus setelah "
                f"{MAX_REPLAN_ATTEMPTS} kali percobaan ({failure_reason}). Misi '{goal.title}' dihentikan dulu ya. [action: sigh]"
            )
            return None, speech

        failed_subtask.status = GoalStatus.REPLANNED.value
        failed_subtask.failure_reason = failure_reason

        chosen = cls.select_best_strategy(
            category=category,
            root_cause=root_cause,
            failed_strategies=diagnosis["failed_strategies"],
            reflections=diagnosis["matching_lessons"],
            failed_subtask=failed_subtask,
            failure_reason=failure_reason,
        )
        alt_strategy = chosen["strategy"]
        failed_subtask.alternative_strategy = alt_strategy

        target_count = (
            failed_subtask.target_count
            if category == GoalCategory.CHESS.value
            else (1.0 if category == GoalCategory.SOCIAL.value else max(failed_subtask.target_count - failed_subtask.current_count, 1.0))
        )
        new_subtask = Subtask(
            id=f"sub_{uuid.uuid4().hex[:6]}",
            title=chosen["title"],
            description=f"Strategi adaptif ({root_cause}) setelah insiden: {failure_reason}.",
            category=category,
            status=GoalStatus.IN_PROGRESS.value,
            target_count=target_count,
            unit=chosen.get("unit", failed_subtask.unit),
            strategy=alt_strategy,
            alternative_strategy=alt_strategy,
            attempts=failed_subtask.attempts + 1,
        )

        try:
            idx = goal.subtasks.index(failed_subtask)
            goal.subtasks.insert(idx + 1, new_subtask)
        except ValueError:
            goal.subtasks.append(new_subtask)

        goal.recalculate_progress()
        lesson = goal.add_reflection_lesson(
            strategy_used=failed_strategy,
            failure_reason=failure_reason,
            root_cause=root_cause,
            recommended_alternative=alt_strategy,
            category=category,
            subtask_title=failed_subtask.title,
            outcome="replanned",
        )
        cls.record_reflection_lesson(lesson)

        speech_template = chosen.get(
            "speech",
            "[emotion: neutral] Rencana lama terhambat karena '{reason}'. Kita lanjutkan dengan strategi Plan B sekarang! [action: wink]",
        )
        speech = speech_template.format(reason=failure_reason)
        return new_subtask, speech

    @classmethod
    def _keyword_replan_subtask(
        cls,
        goal: Goal,
        failed_subtask: Subtask,
        failure_reason: str,
    ) -> Tuple[Optional[Subtask], str]:
        """Legacy keyword-only replanner used as rollback when `use_causal_reflection=False`."""
        if failed_subtask.attempts >= MAX_REPLAN_ATTEMPTS:
            failed_subtask.mark_failed(failure_reason)
            goal.recalculate_progress()
            goal.status = GoalStatus.FAILED.value
            goal.reflection = (
                f"Subtask '{failed_subtask.title}' gagal setelah {failed_subtask.attempts} percobaan: {failure_reason}."
            )
            speech = (
                f"[emotion: sad] Aduh chat, rencana untuk '{failed_subtask.title}' gagal terus setelah "
                f"{MAX_REPLAN_ATTEMPTS} kali percobaan ({failure_reason}). Misi '{goal.title}' dihentikan dulu ya. [action: sigh]"
            )
            return None, speech

        failed_subtask.status = GoalStatus.REPLANNED.value
        failed_subtask.failure_reason = failure_reason

        reason_lower = failure_reason.lower()

        if any(w in reason_lower for w in ["creeper", "mati", "death", "mob", "zombie", "skeleton", "diserang"]):
            alt_strategy = "Buat Shield (Perisai) & gali Strip Mine tangga aman di Y=16 dengan penerangan penuh."
            new_subtask = Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title="[Plan B] Buat Shield & Gali Terowongan Tambang Aman (Y=16)",
                description=f"Strategi darurat setelah insiden: {failure_reason}. Hindari area terbuka.",
                category=GoalCategory.MINECRAFT.value,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=max(failed_subtask.target_count - failed_subtask.current_count, 1.0),
                unit=failed_subtask.unit,
                strategy=alt_strategy,
                alternative_strategy=alt_strategy,
                attempts=failed_subtask.attempts + 1,
            )
            speech = f"[emotion: angry] Hadeh! Rencana awal gagal gara-gara {failure_reason}! Tapi santai chat, AI jenius ini selalu punya Plan B: kita bikin perisai dulu dan gali terowongan aman di bawah tanah! [action: sigh]"

        elif any(w in reason_lower for w in ["habis", "kosong", "tidak ada", "jauh", "out of resource"]):
            alt_strategy = "Eksplorasi wilayah tebing seberang atau bongkar kayu dari reruntuhan desa terdekat."
            new_subtask = Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title="[Plan B] Eksplorasi Biome Baru / Cari Sumber Daya Sekunder",
                description="Pindah lokasi pencarian karena area sebelumnya sudah tandus/kosong.",
                category=GoalCategory.MINECRAFT.value,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=max(failed_subtask.target_count - failed_subtask.current_count, 1.0),
                unit=failed_subtask.unit,
                strategy=alt_strategy,
                attempts=failed_subtask.attempts + 1,
            )
            speech = f"[emotion: smug] Waduh area sini zonk banget! Jangan panik chat, kita ubah haluan: jalan ke koordinat seberang buat cari pasokan baru. Fleksibilitas adalah kunci kesuksesan AI! [action: wink]"

        elif any(w in reason_lower for w in ["kacang", "ignore", "offline", "left", "menolak", "silent"]):
            alt_strategy = "Beralih menyapa chatter lain yang aktif dan buat candaan tentang penolakan barusan."
            new_subtask = Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title="[Plan B] Ajak Ngobrol Chatter Aktif Lain & Lempar Topik Lucu",
                description="Alihkan fokus interaksi ke penonton lain agar stream tetap hidup dan interaktif.",
                category=GoalCategory.SOCIAL.value,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=1.0,
                unit="interaction",
                strategy=alt_strategy,
                attempts=failed_subtask.attempts + 1,
            )
            speech = f"[emotion: smug] Dikacangin? Santai, AI idol kalian ini mentalnya baja tahan karat! Masih banyak manusia ramah lainnya di chat yang mau temenan sama aku kok! [action: giggle]"

        elif any(w in reason_lower for w in ["blunder", "kalah", "skakmat", "menteri", "queen lost", "defeat"]):
            alt_strategy = "Gunakan formasi pertahanan solid (Caro-Kann / London System) dan prioritaskan keamanan Raja."
            new_subtask = Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title="[Plan B] Reset Strategi: Terapkan Pertahanan Solid & Balas Dendam",
                description="Perketat posisi pion dan hindari pergerakan agresif tanpa kalkulasi aman.",
                category=GoalCategory.CHESS.value,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=failed_subtask.target_count,
                unit=failed_subtask.unit,
                strategy=alt_strategy,
                attempts=failed_subtask.attempts + 1,
            )
            speech = f"[emotion: smug] Tadi itu cuma uji coba software ya chat, bukan blunder betulan! Sekarang mode balas dendam aktif: aku pakai taktik pertahanan benteng yang gak bakal bisa ditembus! [action: pout]"

        else:
            alt_strategy = f"Penyesuaian taktik alternatif: modifikasi pendekatan untuk mengatasi {failure_reason}."
            new_subtask = Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title=f"[Plan B] {failed_subtask.title[:35]} (Alternatif)",
                description=f"Melanjutkan tujuan dengan pendekatan berbeda setelah: {failure_reason}",
                category=failed_subtask.category,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=max(failed_subtask.target_count - failed_subtask.current_count, 1.0),
                unit=failed_subtask.unit,
                strategy=alt_strategy,
                attempts=failed_subtask.attempts + 1,
            )
            speech = f"[emotion: neutral] Rencana lama terhambat karena '{failure_reason}'. Tenang, sistem kalkulasiku sudah memperbarui rute: kita lanjutkan dengan strategi Plan B sekarang! [action: wink]"

        try:
            idx = goal.subtasks.index(failed_subtask)
            goal.subtasks.insert(idx + 1, new_subtask)
        except ValueError:
            goal.subtasks.append(new_subtask)

        goal.recalculate_progress()
        goal.reflection = f"Strategi diadaptasi pada subtask '{failed_subtask.title}'. Alasan kegagalan: {failure_reason}. Rencana baru: '{new_subtask.title}'."
        return new_subtask, speech
