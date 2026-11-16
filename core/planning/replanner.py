import uuid
from typing import Tuple, Optional
from core.planning.models import Goal, Subtask, GoalStatus, GoalCategory


class StrategyReplanner:
    """
    Handles dynamic strategy adaptation when a subtask or plan encounters failure.
    Analyzes the failure reason, pivots the strategy, inserts replacement subtasks,
    and produces entertaining streamer commentary explaining the strategic pivot.
    """

    @classmethod
    def replan_subtask(
        cls,
        goal: Goal,
        failed_subtask: Subtask,
        failure_reason: str
    ) -> Tuple[Subtask, str]:
        """
        Adapts the plan by marking the failed subtask, creating a smart alternative subtask,
        and returning (new_subtask, speech_commentary).
        """
        failed_subtask.status = GoalStatus.REPLANNED.value
        failed_subtask.failure_reason = failure_reason

        reason_lower = failure_reason.lower()
        title_lower = failed_subtask.title.lower()

        # 1. Minecraft: Monster attack / Creeper / Death during mining or gathering
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
                attempts=failed_subtask.attempts + 1
            )
            speech = f"[emotion: angry] Hadeh! Rencana awal gagal gara-gara {failure_reason}! Tapi santai chat, AI jenius ini selalu punya Plan B: kita bikin perisai dulu dan gali terowongan aman di bawah tanah! [action: sigh]"

        # 2. Minecraft: Kayu atau sumber daya habis / tidak ditemukan
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
                attempts=failed_subtask.attempts + 1
            )
            speech = f"[emotion: smug] Waduh area sini zonk banget! Jangan panik chat, kita ubah haluan: jalan ke koordinat seberang buat cari pasokan baru. Fleksibilitas adalah kunci kesuksesan AI! [action: wink]"

        # 3. Social: Player tidak merespons atau offline
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
                attempts=failed_subtask.attempts + 1
            )
            speech = f"[emotion: smug] Dikacangin? Santai, AI idol kalian ini mentalnya baja tahan karat! Masih banyak manusia ramah lainnya di chat yang mau temenan sama aku kok! [action: giggle]"

        # 4. Chess: Kalah atau blunder fatal
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
                attempts=failed_subtask.attempts + 1
            )
            speech = f"[emotion: smug] Tadi itu cuma uji coba software ya chat, bukan blunder betulan! Sekarang mode balas dendam aktif: aku pakai taktik pertahanan benteng yang gak bakal bisa ditembus! [action: pout]"

        # 5. General Fallback Adaptation
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
                attempts=failed_subtask.attempts + 1
            )
            speech = f"[emotion: neutral] Rencana lama terhambat karena '{failure_reason}'. Tenang, sistem kalkulasiku sudah memperbarui rute: kita lanjutkan dengan strategi Plan B sekarang! [action: wink]"

        # Insert new subtask into goal right after the failed one
        try:
            idx = goal.subtasks.index(failed_subtask)
            goal.subtasks.insert(idx + 1, new_subtask)
        except ValueError:
            goal.subtasks.append(new_subtask)

        goal.recalculate_progress()
        goal.reflection = f"Strategi diadaptasi pada subtask '{failed_subtask.title}'. Alasan kegagalan: {failure_reason}. Rencana baru: '{new_subtask.title}'."
        return new_subtask, speech
