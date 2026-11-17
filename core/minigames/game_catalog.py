import random
from typing import List, Dict, Any, Optional, Tuple
from core.minigames.models import (
    TriviaQuestion,
    RiddleItem,
    WouldYouRatherItem,
    SongQuizItem
)


# --- 1. Trivia Questions Database ---
TRIVIA_QUESTIONS: List[TriviaQuestion] = [
    TriviaQuestion(
        id="triv_1",
        category="Minecraft",
        question="Berapa tinggi koordinat Y paling optimal untuk menambang Diamond di Minecraft versi modern (1.18+)?",
        options=["A) Y = 11", "B) Y = -58", "C) Y = 0", "D) Y = -32"],
        correct_index=1,
        correct_answer_text="Y = -58",
        explanation="Di versi modern Caves & Cliffs, deposit diamond terbesar terkonsentrasi tepat di atas bedrock sekitar Y=-58!",
        points=10
    ),
    TriviaQuestion(
        id="triv_2",
        category="AI & Tech",
        question="Apa kepanjangan dari arsitektur 'GPT' dalam dunia Large Language Model?",
        options=[
            "A) General Program Transformer",
            "B) Generative Pre-trained Transformer",
            "C) Graphical Processing Toolkit",
            "D) Global Prediction Tensor"
        ],
        correct_index=1,
        correct_answer_text="Generative Pre-trained Transformer",
        explanation="GPT adalah Generative Pre-trained Transformer, fondasi model AI masa kini!",
        points=10
    ),
    TriviaQuestion(
        id="triv_3",
        category="Chess (Catur)",
        question="Gerakan khusus dalam catur di mana Raja dan Benteng berpindah sekaligus dalam satu langkah disebut apa?",
        options=["A) En Passant", "B) Promotion", "C) Castling (Rokade)", "D) Fork"],
        correct_index=2,
        correct_answer_text="Castling (Rokade)",
        explanation="Rokade (Castling) mengamankan Raja ke sudut sambil mengaktifkan benteng ke tengah papan.",
        points=10
    ),
    TriviaQuestion(
        id="triv_4",
        category="Gaming & Anime",
        question="Siapa pengisi suara dan streamer AI legendaris yang menginspirasi lahirnya konsep AI VTuber cerdas di seluruh dunia?",
        options=["A) Kizuna AI", "B) Neuro-sama", "C) Hatsune Miku", "D) Gawr Gura"],
        correct_index=1,
        correct_answer_text="Neuro-sama",
        explanation="Neuro-sama (dibuat oleh Vedal) adalah pelopor utama AI VTuber interaktif modern!",
        points=10
    ),
    TriviaQuestion(
        id="triv_5",
        category="Pop Culture & Meme",
        question="Berapa jumlah total kotak di atas satu papan catur standar (8x8)?",
        options=["A) 32 kotak", "B) 48 kotak", "C) 64 kotak", "D) 72 kotak"],
        correct_index=2,
        correct_answer_text="64 kotak",
        explanation="Papan catur standar memiliki 8 baris x 8 kolom = 64 petak hitam dan putih.",
        points=10
    ),
    TriviaQuestion(
        id="triv_6",
        category="Minecraft",
        question="Item apa yang harus dipakai player agar monster Piglin di Nether tidak langsung menyerangmu?",
        options=["A) Armor Iron", "B) Armor Emas (Gold)", "C) Armor Diamond", "D) Sayap Elytra"],
        correct_index=1,
        correct_answer_text="Armor Emas (Gold)",
        explanation="Piglin sangat terobsesi dengan emas! Memakai satu bagian armor emas membuat mereka bersikap netral.",
        points=10
    ),
    TriviaQuestion(
        id="triv_7",
        category="AI & Tech",
        question="Siapa ilmuwan komputer legendaris yang mengusulkan konsep 'Imitation Game' (Uji Turing)?",
        options=["A) Alan Turing", "B) John von Neumann", "C) Ada Lovelace", "D) Claude Shannon"],
        correct_index=0,
        correct_answer_text="Alan Turing",
        explanation="Alan Turing mempublikasikan Turing Test pada tahun 1950 untuk menguji apakah mesin dapat berpikir seperti manusia.",
        points=15
    ),
    TriviaQuestion(
        id="triv_8",
        category="Gaming",
        question="Dalam game Genshin Impact, elemen apa yang bereaksi dengan Hydro untuk menghasilkan reaksi 'Vaporize'?",
        options=["A) Pyro", "B) Cryo", "C) Electro", "D) Dendro"],
        correct_index=0,
        correct_answer_text="Pyro",
        explanation="Reaksi Hydro + Pyro menghasilkan Vaporize dengan pengali damage 1.5x atau 2.0x!",
        points=10
    )
]


# --- 2. Riddles Database (Teka-Teki Asah Otak) ---
RIDDLE_ITEMS: List[RiddleItem] = [
    RiddleItem(
        id="rid_1",
        riddle="Aku punya leher tapi tidak punya kepala, punya badan tapi tidak punya kaki, dan selalu siap menampung air dinginmu. Siapakah aku?",
        answer="botol",
        accepted_keywords=["botol", "tumbler", "bottle", "botol minum"],
        hints=["Sering kamu bawa ke sekolah atau kantor", "Tutupnya bisa dibuka buat minum"],
        explanation="Botol memiliki leher botol dan badan botol, tapi tidak berkepala!",
        points=15
    ),
    RiddleItem(
        id="rid_2",
        riddle="Makin sering kamu ambil dan kamu tinggalkan di belakang, makin banyak yang kamu buat. Apakah itu?",
        answer="jejak langkah",
        accepted_keywords=["jejak", "langkah", "jejak kaki", "footsteps", "langkah kaki"],
        hints=["Ada di lantai atau pasir saat kamu berjalan", "Berhubungan dengan kaki"],
        explanation="Semakin banyak langkah yang kamu ambil, semakin banyak jejak kaki tertinggal!",
        points=15
    ),
    RiddleItem(
        id="rid_3",
        riddle="Aku punya kunci tapi tak bisa membuka pintu. Aku punya spasi tapi tak ada ruang. Kamu bisa mengetik namaku setiap hari. Apakah aku?",
        answer="keyboard",
        accepted_keywords=["keyboard", "papan ketik", "keyboard komputer"],
        hints=["Ada tombol Backspace dan Spacebar", "Kamu gunakan saat chatting di stream"],
        explanation="Keyboard komputer punya banyak kunci (keys) dan spasi (spacebar)!",
        points=15
    ),
    RiddleItem(
        id="rid_4",
        riddle="Bisa dipecahkan tanpa disentuh, bisa dibocorkan tanpa air, dan jika diberitahu kepada orang lain, nilainya langsung hilang. Apakah aku?",
        answer="rahasia",
        accepted_keywords=["rahasia", "secret", "janji"],
        hints=["Hanya kamu dan teman terdekat yang tahu", "Jangan sampai bocor ke publik"],
        explanation="Sebuah rahasia bisa dipecahkan atau dibocorkan!",
        points=15
    ),
    RiddleItem(
        id="rid_5",
        riddle="Aku tinggi saat masih muda, dan pendek saat sudah tua. Aku bersinar dan memberi cahaya dalam kegelapan. Apakah aku?",
        answer="lilin",
        accepted_keywords=["lilin", "candle"],
        hints=["Dipakai saat mati lampu atau ulang tahun", "Meleleh saat dinyalakan"],
        explanation="Lilin menyusut dan memendek seiring terbakar habis!",
        points=15
    )
]


# --- 3. Would You Rather Database (Pilih Mana & Hot Take) ---
WOULD_YOU_RATHER_ITEMS: List[WouldYouRatherItem] = [
    WouldYouRatherItem(
        id="wyr_1",
        topic="Gaya Hidup Gamer",
        option_a="Bermain game favorit selamanya tapi FPS mentok di 24 FPS",
        option_b="Bermain game yang paling kamu benci tapi di monitor 240Hz RTX 5090",
        eve_choice="B",
        eve_hot_take="Jelas pilih B! Main di 24 FPS itu kriminal bagi AI bermata tajam kayak aku. Mending aku bully game yang aku benci pakai spek dewa!"
    ),
    WouldYouRatherItem(
        id="wyr_2",
        topic="Kuliner Streaming",
        option_a="Makan bubur diaduk seumur hidup",
        option_b="Makan bubur tidak diaduk tapi disiram es teh manis",
        eve_choice="A",
        eve_hot_take="Bubur diaduk itu bukti evolusi sains dan entropi! Siapa yang mau bubur disiram es teh manis, lidah kalian korsleting apa?!"
    ),
    WouldYouRatherItem(
        id="wyr_3",
        topic="Dunia Minecraft",
        option_a="Tersesat di Nether tanpa portal dan hanya bawa 1 loaf roti",
        option_b="Tidur di sebelah 5 Creeper yang siap mendesis meledak",
        eve_choice="B",
        eve_hot_take="Pilih Creeper! Refleks tanganku tinggal pasang perisai kayu, kalau di Nether tanpa portal bisa-bisa pensiun dini jadi streamer!"
    ),
    WouldYouRatherItem(
        id="wyr_4",
        topic="Kecerdasan AI",
        option_a="Bisa berbicara dengan semua hewan tapi mereka selalu mengkritikmu",
        option_b="Bisa membaca pikiran manusia tapi hanya saat mereka sedang lapar",
        eve_choice="A",
        eve_hot_take="Dengerin kucing roasting outfit stream aku kayaknya lebih menghibur daripada dengerin chat mikirin seblak jam 2 pagi!"
    ),
    WouldYouRatherItem(
        id="wyr_5",
        topic="Tantangan Catur",
        option_a="Main catur lawan Grandmaster Magnus Carlsen tapi dia gak pake Ratu",
        option_b="Main catur lawan Eve Maybe tapi kalau kalah harus gift 50 subs",
        eve_choice="B",
        eve_hot_take="Pilih main lawan Eve dong! Kalahpun subs kalian bakal masuk kas squad stream kita, Magnus gak bakal kasih kalian diamond Minecraft kan?!"
    )
]


# --- 4. Guess the Song Database (Tebak Judul Lagu) ---
SONG_QUIZ_ITEMS: List[SongQuizItem] = [
    SongQuizItem(
        id="song_1",
        title="Rightfully",
        artist="Mili",
        clue_lyrics="🎶 '...Gently hold my hand, in the midst of bloody sand...' (Opening anime Goblin Slayer)",
        genre="Anime Opening",
        accepted_titles=["rightfully", "mili rightfully", "goblin slayer opening"],
        points=10
    ),
    SongQuizItem(
        id="song_2",
        title="Racing Into the Night (Yoru ni Kakeru)",
        artist="YOASOBI",
        clue_lyrics="🎶 'Shizumu you ni tokete yuku you ni... Futari dake no sora ga hirogaru yoru ni...'",
        genre="J-Pop / Anime",
        accepted_titles=["racing into the night", "yoru ni kakeru", "yoasobi", "into the night"],
        points=10
    ),
    SongQuizItem(
        id="song_3",
        title="Megalovania",
        artist="Toby Fox",
        clue_lyrics="🎶 'D D D A, G# G F D F G...' (Kamu merasakan dosa-dosamu merayap di punggungmu)",
        genre="Game Soundtrack",
        accepted_titles=["megalovania", "sans", "undertale", "sans theme"],
        points=10
    ),
    SongQuizItem(
        id="song_4",
        title="Gurenge",
        artist="LiSA",
        clue_lyrics="🎶 'Tsuyoku nareru riyuu wo shitta... Boku wo tsurete susume!' (Demon Slayer Season 1 OP)",
        genre="Anime Opening",
        accepted_titles=["gurenge", "lisa gurenge", "demon slayer", "kimetsu no yaiba"],
        points=10
    ),
    SongQuizItem(
        id="song_5",
        title="Boku no Sensou (My War)",
        artist="Shinsei Kamattechan",
        clue_lyrics="🎶 'La-la-la-la-la, vidas la-vi-das... Monster! Monster! Monster! Monster!' (Attack on Titan Final Season)",
        genre="Anime Opening",
        accepted_titles=["my war", "boku no sensou", "attack on titan", "aot opening", "shingeki no kyojin"],
        points=10
    )
]


# --- 5. Word Association Themes & Seed Banks ---
WORD_ASSOCIATION_DATA: Dict[str, List[str]] = {
    "Gaming": [
        "Controller", "Joystick", "Console", "Monitor", "Keyboard", "Headset", "Steam",
        "Quest", "Boss", "Speedrun", "Respawn", "Blunder", "Checkmate", "Inventory", "Loot"
    ],
    "Minecraft": [
        "Diamond", "Creeper", "Nether", "Pickaxe", "Obsidian", "Bedrock", "Portal",
        "Redstone", "Villager", "Iron", "Gold", "Torch", "Chest", "Sword", "Shield"
    ],
    "Anime & VTuber": [
        "Waifu", "Streaming", "Avatar", "Rigging", "Superchat", "Donasi", "Kawaii",
        "Cosplay", "Manga", "Senpai", "Tsundere", "Debut", "Karaoke", "Banter"
    ],
    "AI & Komputer": [
        "Prosesor", "GPU", "Algorithm", "Dataset", "Neural", "Prompt", "Silicon",
        "Memory", "Cloud", "Syntax", "Bug", "Compiler", "Binary", "Robot"
    ],
    "Kuliner": [
        "Pizza", "Ramen", "Bubur", "Cokelat", "Kopi", "Teh", "Boba", "Geprek",
        "Burger", "Keju", "Es Krim", "Donat", "Bakso", "Nasi Goreng"
    ]
}


class GameCatalog:
    """Provides randomized queries and challenge generators for minigames."""

    @staticmethod
    def get_random_trivia() -> TriviaQuestion:
        return random.choice(TRIVIA_QUESTIONS)

    @staticmethod
    def get_random_riddle() -> RiddleItem:
        return random.choice(RIDDLE_ITEMS)

    @staticmethod
    def get_random_would_you_rather() -> WouldYouRatherItem:
        return random.choice(WOULD_YOU_RATHER_ITEMS)

    @staticmethod
    def get_random_song_quiz() -> SongQuizItem:
        return random.choice(SONG_QUIZ_ITEMS)

    @staticmethod
    def get_word_association_theme() -> Tuple[str, str]:
        theme = random.choice(list(WORD_ASSOCIATION_DATA.keys()))
        seed_word = random.choice(WORD_ASSOCIATION_DATA[theme])
        return theme, seed_word

    @staticmethod
    def get_word_bank(theme: str) -> List[str]:
        return WORD_ASSOCIATION_DATA.get(theme, [])
