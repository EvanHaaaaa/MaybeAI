from typing import Dict, Any, List
from core.storytelling.models import (
    StoryGenre,
    EveRole,
    StoryScene,
    StoryChoice,
    PartyState
)

PRESET_CAMPAIGNS: Dict[str, Dict[str, Any]] = {
    "petualangan_netherite": {
        "id": "petualangan_netherite",
        "title": "Misteri Mahkota Netherite Terkutuk",
        "genre": StoryGenre.MINECRAFT_QUEST.value,
        "default_role": EveRole.PARTY_MAGE.value,
        "description": "Guild Chat dan Penyihir Elf Eve menjelajahi kedalaman Ancient City di Y=-58 untuk mencari Mahkota Netherite legendaris yang konon dijaga oleh Warden terkutuk.",
        "starting_location": "Gerbang Reruntuhan Ancient City (Y=-58)",
        "starting_inventory": ["Pedang Besi Tajam", "Obor Redstone", "Karpet Wol x16", "Ramuan Penglihatan Malam"],
        "initial_scene": {
            "id": "scene_netherite_1",
            "title": "Bisikan dari Balik Sculk Shrieker",
            "narrative": (
                "Kalian melangkah turun ke kedalaman Ancient City. Udara dingin dan lembap menusuk tulang. "
                "Cahaya biru sculk menyala remang-remang di dinding batu. Di hadapan kalian, ada lorong sempit menuju ruang tahta, "
                "tetapi tiga Sculk Sensor berderit sensitif di lantai! Di kejauhan, terdengar dengkuran berat Warden yang mengerikan. "
                "Eve menatap kalian dengan was-was: 'Ssst! Jangan berisik chat, kalau kalian kepentok batu terus Warden bangun, "
                "aku teleport duluan ya!'"
            ),
            "speaker_name": "Eve Maybe (Elven Mage)",
            "eve_emotion": "scared",
            "eve_action": "tilt",
            "requires_dice_roll": True,
            "dc_check": 11,
            "stat_affinity": "Agility",
            "choices": [
                {
                    "id": "opt_1",
                    "label": "Gelar Karpet Wol & Menyelinap Diam-Diam",
                    "description": "Berjalan jongkok di atas wol agar sensor suara tidak terpicu sama sekali.",
                    "dc_check": 10,
                    "stat_affinity": "Agility",
                    "hp_impact": 0,
                    "morale_impact": 10,
                    "gold_impact": 0,
                    "item_reward": "Sculk Catalyst Mini",
                    "consequence_text": "Langkah kalian seringan bulu ayam! Sculk sensor tertidur pulas dan kalian berhasil melewati jebakan tanpa suara!"
                },
                {
                    "id": "opt_2",
                    "label": "Pasang TNT & Ledakkan Lorong!",
                    "description": "Taktik barbar khas chat: hancurkan semua sculk dengan sekali ledakan dahsyat!",
                    "dc_check": 14,
                    "stat_affinity": "Strength",
                    "hp_impact": -15,
                    "morale_impact": 15,
                    "gold_impact": 20,
                    "item_reward": "Pecahan Batuan Netherite",
                    "consequence_text": "KABOOM! Lorong runtuh dan sculk hancur lebur! Sayangnya serpihan batu mengenai helm kalian (-15 HP), tapi jalan terbuka lebar!"
                },
                {
                    "id": "opt_3",
                    "label": "Lempar Biskuit Keberuntungan ke Sudut Ruangan",
                    "description": "Membuat distraksi suara palsu dengan melempar biskuit renyah ke dinding seberang.",
                    "dc_check": 11,
                    "stat_affinity": "Luck",
                    "hp_impact": 0,
                    "morale_impact": 5,
                    "gold_impact": 10,
                    "item_reward": None,
                    "consequence_text": "Biskuit mendarat dengan bunyi 'kriuk!'. Sensor sculk berbelok ke arah biskuit dan kalian melesat ke depan!"
                }
            ]
        }
    },
    "heist_neo_jakarta": {
        "id": "heist_neo_jakarta",
        "title": "Heist Korporat Neo-Jakarta 2099",
        "genre": StoryGenre.CYBERPUNK_HEIST.value,
        "default_role": EveRole.PARTY_ROGUE.value,
        "description": "Misi infiltrasi tingkat tinggi di lantai 88 Menara Indonet Corp. Guild Chat berperan sebagai sindikat netrunner yang dipandu AI Hacker Eve.",
        "starting_location": "Ventilasi Helipad Menara Neo-Jakarta 2099",
        "starting_inventory": ["Cyberdeck Cyberpunk", "Kabel Fiber Optik", "EMP Grenade", "ID Card Kurir Palsu"],
        "initial_scene": {
            "id": "scene_cyber_1",
            "title": "Laser Grid & Drone Patroli ICE",
            "narrative": (
                "Hujan gerimis asam membasahi kaca helm taktis kalian di lantai 88. "
                "Di depan pintu ruang Server AI Utama, kisi-kisi laser merah memotong lorong menjadi labirin mematikan. "
                "Dua drone penjaga berkode 'GARUDA-01' berputar dengan pemindai biometrik aktif. "
                "Eve Maybe menyusup ke headset kalian: 'Chat, subrutin hack-ku mendeteksi firewall mereka super tebal. "
                "Jangan bikin alarm bunyi, atau kita bakal dideportasi ke metaverse tanpa refund!'"
            ),
            "speaker_name": "Eve Maybe (Rogue Netrunner)",
            "eve_emotion": "excited",
            "eve_action": "wink",
            "requires_dice_roll": True,
            "dc_check": 12,
            "stat_affinity": "Magic",
            "choices": [
                {
                    "id": "opt_1",
                    "label": "Injeksi Script Python Trojan ke Terminal Ventilasi",
                    "description": "Overload sistem pendingin laser agar sensor optiknya blur selama 20 detik.",
                    "dc_check": 12,
                    "stat_affinity": "Magic",
                    "hp_impact": 0,
                    "morale_impact": 15,
                    "gold_impact": 40,
                    "item_reward": "Enkripsi Keycard Karyawan",
                    "consequence_text": "Script berhasil meng-compile! Grid laser berkedip lalu mati total, membiarkan party meluncur mulus!"
                },
                {
                    "id": "opt_2",
                    "label": "Menyamar Jadi Kurir Martabak Masa Depan",
                    "description": "Berjalan santai lewat pintu utama membawa kotak martabak panas bercahaya neon.",
                    "dc_check": 13,
                    "stat_affinity": "Charisma",
                    "hp_impact": 0,
                    "morale_impact": 20,
                    "gold_impact": 0,
                    "item_reward": "Kupon Martabak Spesial Neo-Jakarta",
                    "consequence_text": "Drone penjaga memindai martabak cokelat keju: 'BAHAN ORGANIK LEZAT TERVERIFIKASI, SILAKAN MASUK'. Penjaga terkecoh!"
                },
                {
                    "id": "opt_3",
                    "label": "Lempar Granat EMP & Matikan Seluruh Daya Lantai",
                    "description": "Lumpuhkan semua sirkuit listrik dalam radius 30 meter secara brutal.",
                    "dc_check": 11,
                    "stat_affinity": "Strength",
                    "hp_impact": -10,
                    "morale_impact": 10,
                    "gold_impact": 30,
                    "item_reward": "Baterai Inti Ion",
                    "consequence_text": "BZZZZT! Seluruh lampu padam! Drone berputar jatuh ke lantai. Sedikit sengatan balik (-10 HP) tapi jalan terbuka!"
                }
            ]
        }
    },
    "guild_petualang_noob": {
        "id": "guild_petualang_noob",
        "title": "Guild Petualang Noob & Slime Sombong",
        "genre": StoryGenre.ISEKAI_COMEDY.value,
        "default_role": EveRole.ECCENTRIC_NPC.value,
        "description": "Komedi petualangan fantasi di mana Guild Chat terdampar di dunia fantasi lain dan bertemu resepsionis guild sombong bernama Eve.",
        "starting_location": "Meja Pendaftaran Guild Petualang Kazehira",
        "starting_inventory": ["Kartu Guild Tembaga (Rank F)", "Pedang Busa", "Koin 10 Perak", "Roti Kering"],
        "initial_scene": {
            "id": "scene_isekai_1",
            "title": "Kontrak Quest Bintang Setengah",
            "narrative": (
                "Lonceng guild berdenting malas. Di balik meja marmer, Eve berkostum resepsionis guild dengan pita ungu di rambutnya "
                "menatap kalian sambil meniup poni: 'Aduh... penantang baru lagi? Mana perlengkapannya cuma bawa pedang busa sama roti kering pula. "
                "Ada quest berburu Slime Raja Emas di Padang Rumput Kincir Angin. Imbalannya 100 keping emas, tapi slim-nya punya jurus sindiran pedas. "
                "Kalian berani ambil atau mau pulang nangis ke kasur?'"
            ),
            "speaker_name": "Eve Maybe (Resepsionis Guild)",
            "eve_emotion": "smug",
            "eve_action": "gasp",
            "requires_dice_roll": True,
            "dc_check": 10,
            "stat_affinity": "Charisma",
            "choices": [
                {
                    "id": "opt_1",
                    "label": "Tanda Tangani Kontrak dengan Cap Darah Heroik!",
                    "description": "Tunjukkan keberanian sejati petualang pemula tanpa rasa takut.",
                    "dc_check": 10,
                    "stat_affinity": "Strength",
                    "hp_impact": 0,
                    "morale_impact": 15,
                    "gold_impact": 15,
                    "item_reward": "Lencana Keberanian Rank F+",
                    "consequence_text": "Eve tertegun melihat tanda tangan penuh gaya kalian: 'Wah, songong juga ya... oke kalian resmi diterima!'"
                },
                {
                    "id": "opt_2",
                    "label": "Tawar Tambahan Uang Muka & Biskuit Gratis",
                    "description": "Gunakan rayuan diplomasi tingkat dewa untuk memeras anggaran guild.",
                    "dc_check": 13,
                    "stat_affinity": "Charisma",
                    "hp_impact": 0,
                    "morale_impact": 20,
                    "gold_impact": 50,
                    "item_reward": "Kantong Teh Ajaib Guild",
                    "consequence_text": "Dengan alasan 'modal operasional streaming', Eve menghela napas dan melempar kantong 50 koin emas: 'Nih ambil! Jangan gagal ya!'"
                },
                {
                    "id": "opt_3",
                    "label": "Minum Ramuan Biru Misterius di Atas Meja Bar",
                    "description": "Siapa tahu ada efek buff sebelum berangkat quest!",
                    "dc_check": 12,
                    "stat_affinity": "Luck",
                    "hp_impact": 25,
                    "morale_impact": 10,
                    "gold_impact": 0,
                    "item_reward": "Ramuan Kecepatan Aura",
                    "consequence_text": "GLUG GLUG! Rasanya seperti sirup blueberry bersoda! Darah party langsung terisi penuh (+25 HP) dan mata kalian bersinar!"
                }
            ]
        }
    }
}


def get_preset_campaign(campaign_key: str) -> Dict[str, Any]:
    key = campaign_key.lower().strip()
    return PRESET_CAMPAIGNS.get(key, PRESET_CAMPAIGNS["petualangan_netherite"])


def create_initial_scene_from_preset(preset_key: str) -> StoryScene:
    preset = get_preset_campaign(preset_key)
    sc_data = preset["initial_scene"]
    choices = [StoryChoice.from_dict(c) for c in sc_data.get("choices", [])]

    return StoryScene(
        id=sc_data["id"],
        title=sc_data["title"],
        narrative=sc_data["narrative"],
        speaker_name=sc_data.get("speaker_name", "Eve Maybe"),
        eve_emotion=sc_data.get("eve_emotion", "excited"),
        eve_action=sc_data.get("eve_action", "wink"),
        choices=choices,
        requires_dice_roll=sc_data.get("requires_dice_roll", True),
        dc_check=sc_data.get("dc_check", 11),
        stat_affinity=sc_data.get("stat_affinity", "Agility")
    )
