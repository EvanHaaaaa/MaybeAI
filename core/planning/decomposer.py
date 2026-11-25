import re
import uuid
from typing import List, Dict, Any, Optional
from core.planning.models import Goal, Subtask, GoalTier, GoalCategory, GoalStatus


class GoalDecomposer:
    """
    Intelligently breaks high-level goals into actionable, sequential subtasks.
    Contains specialized decompositions for Minecraft, Chess, Social interactions,
    and Stream challenges, with automated recipe recognition.
    """

    @classmethod
    def decompose(cls, goal_title: str, description: str = "", tier: str = GoalTier.DAILY.value, category: str = GoalCategory.GENERAL.value) -> List[Subtask]:
        lower = (goal_title + " " + description).lower()

        # 1. Minecraft: Membangun rumah (Build House)
        if any(w in lower for w in ["rumah", "house", "base", "shelter", "bangun rumah"]):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Tebang pohon & kumpulkan 32 Oak Logs",
                    description="Kumpulkan kayu gelondongan di sekitar hutan untuk bahan baku papan.",
                    category=GoalCategory.MINECRAFT.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=32.0,
                    unit="logs",
                    strategy="Tebang pohon oak terdekat dengan axe."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Crafting Table & perlengkapan pertukangan",
                    description="Buat Crafting Table, Wooden Pickaxe, dan Wooden Axe.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=1.0,
                    unit="craft",
                    strategy="Olah 4 logs jadi planks, lalu buat meja kerja."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Ratakan tanah & pasang fondasi cobblestone",
                    description="Bersihkan lahan 7x7 blok lalu pasang cobblestone sebagai batas fondasi.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=20.0,
                    unit="cobblestone",
                    strategy="Gali tanah datar dekat sungai atau spawn."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Dirikan dinding kayu & pasang pintu depan",
                    description="Susun dinding kayu oak setinggi 3 blok dan buat pintu kayu.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=30.0,
                    unit="planks",
                    strategy="Susun planks secara simetris dengan bukaan jendela."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Pasang atap dan obor penerangan (Torches)",
                    description="Tutup atap rumah dan letakkan obor di tiap sudut agar mob tidak spawn.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=10.0,
                    unit="torches",
                    strategy="Letakkan obor di dalam rumah dan sekeliling pintu masuk."
                )
            ]

        # 2. Minecraft: Mengumpulkan 64 iron (Mining Iron)
        if any(w in lower for w in ["iron", "besi", "bijih besi", "64 iron"]):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Siapkan Stone Pickaxe & persediaan obor",
                    description="Buat perlengkapan tambang batu dan bawa minimal 16 obor.",
                    category=GoalCategory.MINECRAFT.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=1.0,
                    unit="kit",
                    strategy="Mining batu sebentar untuk upgrade pickaxe dan craft torch dari coal."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Eksplorasi gua atau gali terowongan tambang (Y=16)",
                    description="Temukan bukaan gua alami atau gali staircase menuju kedalaman yang kaya besi.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=1.0,
                    unit="cave",
                    strategy="Cari ravine atau cave entrance di tebing bukit."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Tambang 64 Raw Iron Ore dari dinding gua",
                    description="Kumpulkan 64 bijih besi mentah dari urat-urat besi di gua.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=64.0,
                    unit="iron_ore",
                    strategy="Gali semua urat besi sambil menjaga pencahayaan agar aman dari mob."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Smelt semua bijih besi di Furnace jadi Iron Ingot",
                    description="Masak 64 bijih besi menjadi batangan besi murni siap pakai.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=64.0,
                    unit="iron_ingot",
                    strategy="Buat 2 furnace untuk mempercepat proses peleburan."
                )
            ]

        # 3. Minecraft: Speedrun Challenge (Tujuan Mingguan)
        if any(w in lower for w in ["speedrun", "dragon", "tamatin", "beat game", "ender dragon"]):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Gathering awal & buat Water Bucket",
                    description="Kumpulkan kayu, stone tools, 3 iron ingot, dan isi ember air.",
                    category=GoalCategory.MINECRAFT.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=1.0,
                    unit="bucket",
                    strategy="Serang Iron Golem di desa untuk mendapatkan iron instan."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Bikin Nether Portal dengan lava pool & masuk Nether",
                    description="Gunakan taktik bucket air di atas lava pool untuk membuat portal tanpa diamond pickaxe.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=1.0,
                    unit="portal",
                    strategy="Cari lava pool di danau permukaan, susun cetakan portal obsidian."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Cari Nether Fortress & kumpulkan 7 Blaze Rods",
                    description="Temukan benteng nether dan kalahkan blaze untuk mendapatkan batang api.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=7.0,
                    unit="blaze_rods",
                    strategy="Manfaatkan corner-peeking agar tidak terbakar tembakan bola api blaze."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Barter Ender Pearls & racik Eyes of Ender",
                    description="Tukar emas ke Piglin untuk mendapatkan pearl, lalu cari Stronghold.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=12.0,
                    unit="eyes_of_ender",
                    strategy="Lempar Eye of Ender dan ukur sudut triangulasi."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Aktifkan End Portal & Kalahkan Ender Dragon",
                    description="Masuk ke dimensi The End dan habisi Ender Dragon untuk menamatkan game.",
                    category=GoalCategory.MINECRAFT.value,
                    target_count=1.0,
                    unit="dragon_kill",
                    strategy="Hancurkan end crystal, ledakkan bed saat dragon bertengger di altar."
                )
            ]

        # 4. Social: Berinteraksi dengan player belum dikenal (Tujuan Sosial)
        if any(w in lower for w in ["sosial", "social", "player baru", "kenal", "interaksi", "teman", "penonton baru"]):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Pantau & identifikasi penonton/pemain baru di chat/server",
                    description="Perhatikan username baru yang belum pernah berinteraksi sebelumnya.",
                    category=GoalCategory.SOCIAL.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=1.0,
                    unit="detect",
                    strategy="Filter chat incoming untuk mencari chatter non-veteran."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Beri sapaan hangat & tanyakan kabar/preferensi",
                    description="Sapa mereka secara spesifik dengan nada ceria dan ramah khas VTuber.",
                    category=GoalCategory.SOCIAL.value,
                    target_count=1.0,
                    unit="greeting",
                    strategy="Gunakan sapaan personal: 'Halo [user], selamat datang di stream!'"
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Ajak bermain bersama atau tawarkan bantuan (Minecraft/Catur)",
                    description="Buka kesempatan interaksi dua arah yang seru dan mengasyikkan.",
                    category=GoalCategory.SOCIAL.value,
                    target_count=1.0,
                    unit="collab",
                    strategy="Tawarkan mode guard di Minecraft atau tantangan catur santai."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Rekam preferensi & interaksi ke Second Brain Episodic Memory",
                    description="Simpan data fakta dan hobi mereka ke database memori jangka panjang.",
                    category=GoalCategory.SOCIAL.value,
                    target_count=1.0,
                    unit="memory",
                    strategy="Ekstrak entitas profil penonton ke SQLite dossier."
                )
            ]

        # 5. Chess: ELO & Gameplay Challenge
        if category == GoalCategory.CHESS.value or any(w in lower for w in ["catur", "chess", "skakmat", "grandmaster"]) or re.search(r"\belo\b", lower):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Latihan opening catur yang solid (Sicilian Defense / Italian Game)",
                    description="Siapkan pembukaan taktis untuk mengendalikan petak tengah (center squares).",
                    category=GoalCategory.CHESS.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=1.0,
                    unit="opening",
                    strategy="Buka dengan e4 atau c5 untuk kontrol tempo cepat."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Menangkan 3 pertandingan melawan penonton/challenger",
                    description="Kalahkan lawan dengan kalkulasi tajam tanpa melakukan blunder fatal.",
                    category=GoalCategory.CHESS.value,
                    target_count=3.0,
                    unit="wins",
                    strategy="Eksploitasi kelemahan pion lawan dan lakukan fork ksatria."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Eksekusi skakmat endgame yang bersih & elegan",
                    description="Selesaikan pertandingan dengan kombinasi serangan raja dan menteri.",
                    category=GoalCategory.CHESS.value,
                    target_count=1.0,
                    unit="checkmate",
                    strategy="Kurung raja lawan ke baris belakang menggunakan benteng/menteri."
                )
            ]

        # 6. Performance / Karaoke Idol Challenge
        if category == GoalCategory.PERFORMANCE.value or any(w in lower for w in ["konser", "karaoke", "nyanyi", "lagu", "setlist", "performance"]):
            return [
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Pilih lagu & susun setlist konser sesuai mood stream",
                    description="Kurasi lagu pembuka dan atur urutan penampilan bersama PerformanceDirector.",
                    category=GoalCategory.PERFORMANCE.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=1.0,
                    unit="setlist",
                    strategy="Cek mood dominan lalu pilih lagu yang paling cocok dengan energi chat."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="MC Pembuka & ajak penonton nyalakan glowstick",
                    description="Sapa penonton, buka sesi karaoke, dan bangun hype di panggung.",
                    category=GoalCategory.PERFORMANCE.value,
                    target_count=1.0,
                    unit="mc_intro",
                    strategy="Gunakan sapaan idol yang ceria dan panggil chat memakai !glowstick."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Nyanyikan lagu utama dengan koreografi live",
                    description="Tampil menyanyikan lagu pilihan dengan ekspresi avatar dan sinkronisasi lirik.",
                    category=GoalCategory.PERFORMANCE.value,
                    target_count=1.0,
                    unit="song",
                    strategy="Ikuti tempo musik dan sinkronkan gerakan panggung di setiap section."
                ),
                Subtask(
                    id=f"sub_{uuid.uuid4().hex[:6]}",
                    title="Raih sorakan glowstick & tutup konser dengan encore",
                    description="Evaluasi skor penampilan panggung dan ucapkan terima kasih kepada chat.",
                    category=GoalCategory.PERFORMANCE.value,
                    target_count=1.0,
                    unit="glowsticks",
                    strategy="Rayakan pencapaian skor panggung dan tawarkan lagu encore."
                )
            ]

        # 7. Generic / Custom Fallback Decomposition
        return [
            Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title=f"Tahap 1: Persiapan & strategi '{goal_title[:30]}'",
                description="Kumpulkan informasi, peralatan, dan tentukan langkah awal pengerjaan.",
                category=category,
                status=GoalStatus.IN_PROGRESS.value,
                target_count=1.0,
                unit="prep",
                strategy="Tentukan prioritas awal dan persiapkan sumber daya pendukung."
            ),
            Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title=f"Tahap 2: Eksekusi inti '{goal_title[:30]}'",
                description="Lakukan aktivitas utama secara konsisten untuk mencapai target.",
                category=category,
                target_count=1.0,
                unit="action",
                strategy="Fokus pada pengerjaan inti secara berkesinambungan."
            ),
            Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title=f"Tahap 3: Evaluasi progres & penyesuaian taktik",
                description="Periksa apakah langkah awal berhasil atau perlu adaptasi strategi.",
                category=category,
                target_count=1.0,
                unit="eval",
                strategy="Cek hasil sementara dan atasi kendala yang muncul."
            ),
            Subtask(
                id=f"sub_{uuid.uuid4().hex[:6]}",
                title=f"Tahap 4: Finalisasi & rayakan pencapaian target",
                description="Selesaikan detail akhir dan umumkan keberhasilan ke penonton stream.",
                category=category,
                target_count=1.0,
                unit="complete",
                strategy="Rayakan keberhasilan bersama chat dan catat ke memori."
            )
        ]
