import json
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from core.storytelling.models import (
    StoryGenre,
    EveRole,
    CampaignStatus,
    StoryChoice,
    PartyState,
    DiceRollResult,
    StoryScene,
    CampaignSession
)
from core.storytelling.preset_campaigns import (
    PRESET_CAMPAIGNS,
    get_preset_campaign,
    create_initial_scene_from_preset
)


class StoryEngine:
    """
    Dynamic Storytelling & Community Roleplay Engine.
    Allows Eve to host live interactive RPGs and stories with stream viewers.
    Supports branching choices, community chat voting, D20 dice checks,
    party stats, episodic memory continuity, and Second Brain synchronization.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        second_brain_dir: str = "data/second_brain",
        data_dir: Optional[str] = None
    ):
        if storage_path is None:
            if data_dir:
                storage_path = str(Path(data_dir) / "campaigns.json")
            else:
                storage_path = "data/storytelling/campaigns.json"

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if data_dir and second_brain_dir == "data/second_brain":
            self.second_brain_dir = Path(data_dir) / "second_brain"
        else:
            self.second_brain_dir = Path(second_brain_dir)

        self.session: CampaignSession = CampaignSession()
        self.campaigns_history: List[Dict[str, Any]] = []

        self._load_or_seed()
        self.sync_to_second_brain()

    def _load_or_seed(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "active_session" in data and data["active_session"]:
                        self.session = CampaignSession.from_dict(data["active_session"])
                    self.campaigns_history = data.get("history", [])
            except Exception as e:
                print(f"[StoryEngine] Error loading storytelling data: {e}")
                self._seed_default_state()
        else:
            self._seed_default_state()
        self.save()

    def _seed_default_state(self):
        self.session = CampaignSession(
            title="Misteri Mahkota Netherite Terkutuk",
            genre=StoryGenre.MINECRAFT_QUEST.value,
            eve_role=EveRole.PARTY_MAGE.value,
            status=CampaignStatus.IDLE.value,
            key_memories=[
                "Guild Chat pernah mengalahkan Mimic berkat voting lempar biskuit",
                "Eve hampir membakar jenggot kurcaci dengan spell api level 1"
            ]
        )
        self.campaigns_history = [
            {
                "id": "campaign_arch_001",
                "title": "Pelarian dari Penjara Dungeon Abyss",
                "genre": "fantasy_rpg",
                "episodes": 4,
                "winner": "Guild Chat & Eve",
                "summary": "Chat memilih menjebol dinding sendok dan Eve melempar glitter blind spell ke sipir ogre.",
                "completed_at": time.strftime("%Y-%m-%d")
            }
        ]

    def save(self):
        try:
            data = {
                "active_session": self.session.to_dict(),
                "history": self.campaigns_history
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[StoryEngine] Error saving storytelling data: {e}")

    # --- Campaign Lifecycle ---
    def start_campaign(
        self,
        campaign_preset: str = "petualangan_netherite",
        genre: Optional[str] = None,
        eve_role: Optional[str] = None,
        custom_title: Optional[str] = None,
        custom_premise: Optional[str] = None
    ) -> Tuple[CampaignSession, str]:
        """Starts a fresh interactive story/roleplay campaign."""
        clean_preset = campaign_preset.strip().lower()

        if clean_preset in PRESET_CAMPAIGNS:
            preset = get_preset_campaign(clean_preset)
            title = custom_title or preset["title"]
            g = genre or preset["genre"]
            role = eve_role or preset["default_role"]
            init_scene = create_initial_scene_from_preset(clean_preset)
            init_party = PartyState(
                name=f"Guild {title.split()[0]} & Eve",
                hp=100,
                morale=100,
                gold=50,
                inventory=list(preset.get("starting_inventory", ["Pedang Kayu", "Obor"])),
                current_location=preset.get("starting_location", "Pintu Masuk Quest")
            )
        else:
            title = custom_title or "Petualangan Bebas Komunitas"
            g = genre or StoryGenre.FANTASY_RPG.value
            role = eve_role or EveRole.DUNGEON_MASTER.value
            init_party = PartyState()
            init_scene = StoryScene(
                id=f"scene_{int(time.time())}",
                title="Prolog: Pertemuan Awal",
                narrative=custom_premise or (
                    "Kalian berkumpul di sekitar api unggun. Angin malam berhembus lembut. "
                    "Eve tersenyum penuh rahasia: 'Petualangan baru kita dimulai malam ini, chat! "
                    "Kemana tujuan pertama guild kita?'"
                ),
                speaker_name=f"Eve Maybe ({role.replace('_', ' ').title()})",
                eve_emotion="excited",
                eve_action="wink",
                choices=[
                    StoryChoice(
                        id="opt_1",
                        label="Jelajahi Hutan Terlarang",
                        description="Masuk ke dalam hutan lebat penuh kabut sihir.",
                        dc_check=11,
                        stat_affinity="Agility"
                    ),
                    StoryChoice(
                        id="opt_2",
                        label="Menuju Kota Bawah Tanah",
                        description="Mencari pemandu kurcaci di pasar gelap.",
                        dc_check=12,
                        stat_affinity="Charisma"
                    ),
                    StoryChoice(
                        id="opt_3",
                        label="Istirahat & Siapkan Perbekalan",
                        description="Bikin sup jamur dan seduh teh hangat dulu.",
                        dc_check=10,
                        stat_affinity="Luck"
                    )
                ]
            )

        self.session = CampaignSession(
            title=title,
            genre=g,
            eve_role=role,
            status=CampaignStatus.VOTING.value,
            current_scene=init_scene,
            scenes_history=[],
            party=init_party,
            freeform_suggestions=[],
            last_dice_roll=None,
            total_episodes_completed=self.session.total_episodes_completed if self.session else 0,
            key_memories=list(self.session.key_memories) if self.session else []
        )

        speech = (
            f"[emotion: excited] Petualangan RPG Dimulai: **{title}**! [action: wink] "
            f"Di petualangan ini, Eve berperan sebagai **{role.replace('_', ' ').title()}**! "
            f"Chat, kalian adalah anggota guild terhebatku! Ketik '!1', '!2', atau '!3' untuk vote keputusan, "
            f"atau ajukan aksi gila kalian dengan '!action [tindakan]'! Let's go!"
        )

        self.save()
        self.sync_to_second_brain()
        return self.session, speech

    # --- Chat Input Processing ---
    def process_chat_input(self, user: str, message: str) -> Optional[Tuple[bool, str]]:
        """
        Processes chat commands during active storytelling:
        - !1, !2, !3 or options
        - !action or !aksi for freeform creative proposals
        - !roll, !d20, !dadu for dice rolling
        """
        if self.session.status == CampaignStatus.IDLE.value or self.session.status == CampaignStatus.COMPLETED.value:
            return None

        clean = message.strip()
        lower = clean.lower()

        # 1. Roll Dice command
        if any(w in lower for w in ["!roll", "!d20", "!dadu", "/roll"]):
            res, speech = self.roll_dice(roller=user)
            return True, speech

        # 2. Freeform Action Proposal
        if lower.startswith("!action") or lower.startswith("!aksi") or lower.startswith("!act"):
            parts = clean.split(" ", 1)
            action_text = parts[1].strip() if len(parts) > 1 else ""
            if action_text:
                ok, speech = self.submit_freeform_action(user, action_text)
                return ok, speech

        # 3. Choice Voting
        opt_chosen = None
        if lower in ["!1", "1", "!a", "opsi 1", "pilih 1", "pilihan 1"]:
            opt_chosen = "opt_1"
        elif lower in ["!2", "2", "!b", "opsi 2", "pilih 2", "pilihan 2"]:
            opt_chosen = "opt_2"
        elif lower in ["!3", "3", "!c", "opsi 3", "pilih 3", "pilihan 3"]:
            opt_chosen = "opt_3"
        else:
            # Check match against choice text or opt_id
            if self.session.current_scene:
                for idx, c in enumerate(self.session.current_scene.choices):
                    if c.id.lower() == lower or c.label.lower() in lower:
                        opt_chosen = c.id
                        break

        if opt_chosen:
            ok, speech = self.vote_choice(user, opt_chosen)
            return ok, speech

        return None

    # --- Choice Voting & Freeform Proposals ---
    def vote_choice(self, user: str, choice_id: str) -> Tuple[bool, str]:
        sc = self.session.current_scene
        if not sc or not sc.choices:
            return False, "[emotion: confused] Belum ada pilihan yang aktif untuk di-vote saat ini! [action: shrug]"

        target_choice = None
        for c in sc.choices:
            if c.id == choice_id:
                target_choice = c
                break

        if not target_choice:
            return False, f"[emotion: confused] Pilihan '{choice_id}' tidak ditemukan di adegan ini! [action: shrug]"

        # Remove previous vote by this user across all choices in this scene
        for c in sc.choices:
            if user in c.votes:
                c.votes.remove(user)

        target_choice.votes.append(user)
        self.session.updated_at = time.time()
        self.save()

        # Calculate tally
        tally = " | ".join([f"{c.label[:20]}...: {len(c.votes)} vote" for c in sc.choices])
        speech = (
            f"[emotion: happy] Suara {user} tercatat untuk: **{target_choice.label}**! "
            f"Perolehan suara saat ini: ({tally}). Ayo chat lain segera vote! [action: wink]"
        )
        return True, speech

    def submit_freeform_action(self, user: str, action_text: str) -> Tuple[bool, str]:
        clean = action_text.strip()
        if len(clean) < 3:
            return False, "[emotion: neutral] Tuliskan aksi kreatif yang lebih jelas, chat! [action: tilt]"

        # Store suggestion
        entry = {
            "id": f"act_{len(self.session.freeform_suggestions) + 1}",
            "user": user,
            "action": clean,
            "votes": [user],
            "time": time.strftime("%H:%M:%S")
        }
        self.session.freeform_suggestions.append(entry)
        self.session.updated_at = time.time()
        self.save()

        speech = (
            f"[emotion: excited] Ide menarik dari {user}: '*{clean}*!' "
            f"Ide ini masuk ke opsi strategi darurat guild! Ada yang mau dukung ide {user}? [action: wink]"
        )
        return True, speech

    # --- D20 Dice Rolling ---
    def roll_dice(
        self,
        roller: str = "Chat",
        dc_target: Optional[int] = None,
        stat_type: Optional[str] = None
    ) -> Tuple[DiceRollResult, str]:
        """Rolls a D20 with DC check and roleplay reaction."""
        sc = self.session.current_scene
        dc = dc_target if dc_target is not None else (sc.dc_check if sc else 11)
        stat = stat_type or (sc.stat_affinity if sc else "Luck")

        # Roll natural D20
        d20 = random.randint(1, 20)

        # Modifier based on party morale (+1 if morale >= 75, -1 if morale < 40)
        modifier = 0
        if self.session.party.morale >= 80:
            modifier += 2
        elif self.session.party.morale >= 50:
            modifier += 1
        elif self.session.party.morale < 30:
            modifier -= 2

        total = d20 + modifier
        is_crit_succ = (d20 == 20)
        is_crit_fail = (d20 == 1)
        is_success = is_crit_succ or (total >= dc and not is_crit_fail)

        if is_crit_succ:
            outcome = "NATURAL 20! Keberhasilan mutlak dan spektakuler! Keberuntungan dewa memihak kita!"
            speech = (
                f"[emotion: excited] 🎲 CRITICAL SUCCESS! NATURAL 20 DARI {roller.upper()}! [action: gasp] "
                f"Sihir meledak dengan indah, rencana berhasil 1000%! Party dapat bonus moral & harta ekstra! 🎉"
            )
            self.session.party.apply_impact(hp_delta=10, morale_delta=20, gold_delta=25)
        elif is_crit_fail:
            outcome = "NATURAL 1! Kegagalan kritis yang memalukan tapi kocak! Terpeleset kulit pisang kosmik!"
            speech = (
                f"[emotion: surprised] 🎲 NATURAL 1 DARI {roller.upper()}! ADUUUH BLUNDER BESAR! [action: pout] "
                f"Pedang nyangkut di langit-langit, celana robek, dan alarm musuh berbunyi nyaring! (-10 HP) 😭"
            )
            self.session.party.apply_impact(hp_delta=-10, morale_delta=-15)
        elif is_success:
            outcome = f"BERHASIL! Total {total} vs DC {dc}. Rencana terlaksana dengan mulus."
            speech = (
                f"[emotion: happy] 🎲 DADU D20: {d20} (+{modifier} bonus) = **{total}**! (DC {dc}) [action: wink] "
                f"Target tercapai! Guild kita berhasil mengeksekusi strategi dengan mulus!"
            )
            self.session.party.apply_impact(morale_delta=5)
        else:
            outcome = f"GAGAL! Total {total} vs DC {dc}. Terkena sedikit serangan balasan."
            speech = (
                f"[emotion: smug] 🎲 DADU D20: {d20} (+{modifier} bonus) = **{total}**... Sayang sekali di bawah DC {dc}! [action: giggle] "
                f"Kalian tersandung tapi masih bisa bertahan! Darah party berkurang sedikit (-5 HP)!"
            )
            self.session.party.apply_impact(hp_delta=-5, morale_delta=-5)

        res = DiceRollResult(
            roller=roller,
            d20_value=d20,
            modifier=modifier,
            total=total,
            dc_target=dc,
            stat_type=stat,
            is_critical_success=is_crit_succ,
            is_critical_fail=is_crit_fail,
            is_success=is_success,
            outcome_text=outcome
        )

        self.session.last_dice_roll = res
        if sc:
            sc.dice_result = res
        self.session.updated_at = time.time()
        self.save()

        return res, speech

    # --- Scene Progression ---
    def advance_scene(
        self,
        chosen_choice_id: Optional[str] = None,
        custom_narrative: Optional[str] = None
    ) -> Tuple[StoryScene, str]:
        """Resolves active scene and advances to the next chapter."""
        cur_sc = self.session.current_scene
        if not cur_sc:
            return self.session.current_scene, "Tidak ada scene aktif."

        # Determine winning choice: either explicit or highest votes
        selected_choice: Optional[StoryChoice] = None
        if chosen_choice_id:
            for c in cur_sc.choices:
                if c.id == chosen_choice_id:
                    selected_choice = c
                    break

        if not selected_choice and cur_sc.choices:
            # Pick choice with most votes, fallback to random
            sorted_choices = sorted(cur_sc.choices, key=lambda c: len(c.votes), reverse=True)
            selected_choice = sorted_choices[0]

        consequence_narrative = ""
        if selected_choice:
            cur_sc.resolved_choice_id = selected_choice.id
            self.session.party.apply_impact(
                hp_delta=selected_choice.hp_impact,
                morale_delta=selected_choice.morale_impact,
                gold_delta=selected_choice.gold_impact,
                item_add=selected_choice.item_reward
            )
            consequence_narrative = selected_choice.consequence_text or f"Kalian memutuskan: {selected_choice.label}."

        # Save to scenes history
        self.session.scenes_history.append(cur_sc)

        # Generate next scene
        scene_idx = len(self.session.scenes_history) + 1
        g = self.session.genre

        if custom_narrative:
            next_narrative = custom_narrative
            next_title = f"Babak {scene_idx}: Kelanjutan Tak Terduga"
        else:
            next_narrative, next_title = self._generate_next_story_beat(scene_idx, selected_choice)

        next_choices = self._generate_choices_for_beat(scene_idx, g)

        new_scene = StoryScene(
            id=f"scene_{int(time.time())}_{scene_idx}",
            title=next_title,
            narrative=f"{consequence_narrative} {next_narrative}".strip(),
            speaker_name=f"Eve Maybe ({self.session.eve_role.replace('_', ' ').title()})",
            eve_emotion="excited" if self.session.party.hp > 40 else "scared",
            eve_action="wink",
            choices=next_choices,
            requires_dice_roll=True,
            dc_check=11 + scene_idx,
            stat_affinity="Strength" if scene_idx % 2 == 0 else "Agility"
        )

        self.session.current_scene = new_scene
        self.session.status = CampaignStatus.VOTING.value
        self.session.freeform_suggestions = []
        self.session.updated_at = time.time()

        # Check if party defeated or reached climax
        if self.session.party.hp <= 0:
            return self.end_campaign(outcome_summary="Party kehabisan darah dan harus dievakuasi oleh guild medis!")

        speech = (
            f"[emotion: excited] Babak Baru: **{next_title}**! [action: wink]\n"
            f"{new_scene.narrative}\n"
            f"Darah Party: {self.session.party.hp}/100 HP | Gold: {self.session.party.gold}G | Lokasi: {self.session.party.current_location}. "
            f"Ayo vote keputusan kalian selanjutnya di chat!"
        )

        self.save()
        self.sync_to_second_brain()
        return new_scene, speech

    def _generate_next_story_beat(self, scene_idx: int, prev_choice: Optional[StoryChoice]) -> Tuple[str, str]:
        g = self.session.genre
        role = self.session.eve_role

        if g == StoryGenre.MINECRAFT_QUEST.value:
            if scene_idx == 2:
                self.session.party.current_location = "Ruang Tahta Reruntuhan Sculk"
                return (
                    "Kalian tiba di tengah plaza Ancient City. Di tengah kegelapan, sebuah peti berkilauan warna biru tua: "
                    "Mahkota Netherite Terkutuk tergeletak di atas altar! Namun di sebelah altar, Warden raksasa sedang "
                    "mengendus-ngendus bau keringat kalian! Eve berbisik panik: 'Chat, dia mulai ngendus kita! "
                    "Apa strategi pamungkas kita sebelum dia ngamuk?!'",
                    "Babak 2: Di Hadapan Sang Penjaga Kegelapan"
                )
            elif scene_idx == 3:
                self.session.party.current_location = "Portal Kuno Netherite"
                return (
                    "Altar bergetar hebat saat kalian menyentuh mahkota! Portal batu raksasa di depan kalian mulai menyala dengan api biru. "
                    "Warden meraung keras memanggil pasukan sculk! Jalan keluar runtuh, satu-satunya jalan hidup adalah melompat ke portal misterius!",
                    "Babak 3: Puncak Pertarungan & Portal Misterius"
                )
            else:
                return (
                    "Kalian berhasil mengamankan artefak dan keluar dari Ancient City disambut cahaya matahari pagi! "
                    "Semua penduduk desa bersorak memuji ketangguhan Guild Chat dan Eve Maybe!",
                    "Epilog: Kemenangan Sang Pahlawan"
                )

        elif g == StoryGenre.CYBERPUNK_HEIST.value:
            if scene_idx == 2:
                self.session.party.current_location = "Ruang Server Inti Lantai 88"
                return (
                    "Kalian berhasil menembus pintu lapis baja! Di hadapan kalian berdiri superkomputer berkilau hologram: "
                    "Kecerdasan Buatan Korporat 'GATOTKACA-v9'. Suara digital menggelegar: 'PENYUSUP TERDETEKSI. "
                    "MEMULAI PROTOKOL PEMBASMIAN NETRUNNER.' Eve buru-buru memasang kabel bypass: 'Chat, bantu aku tembus ICE-nya!'",
                    "Babak 2: Duel Hacker vs AI Korporat"
                )
            else:
                self.session.party.current_location = "Taksi Terbang Menembus Malam"
                return (
                    "Data rahasia sukses diunduh ke flashdisk kucing Eve! Sirene polisi udara bergaung di luar jendela. "
                    "Sebuah taksi terbang tanpa sopir melayang di luar jendela pecah. Saatnya lompat dan kabur!",
                    "Babak 3: Kejar-kejaran Taksi Terbang Neo-Jakarta"
                )
        else:
            if scene_idx == 2:
                self.session.party.current_location = "Sarang Monster Kincir Angin"
                return (
                    "Kalian tiba di padang rumput dan dihadang oleh Slime Emas raksasa bertopi koboi! "
                    "Slime itu berkacak pinggang: 'Hohoho! Kalian mau mengalahkanku? Sebelum bertarung, jawab dulu 3 pantun mautku!' "
                    "Eve menatap kalian: 'Buset, monsternya jago pantun chat... kita bales apa kita serang langsung nih?'",
                    "Babak 2: Tantangan Sang Slime Koboi"
                )
            else:
                self.session.party.current_location = "Perjamuan Kemenangan Guild"
                return (
                    "Petualangan berakhir dengan gelak tawa! Slime emas menyerah dan malah mentraktir kalian sate kelinci di kedai kota. "
                    "Eve tersenyum puas menghitung tumpukan koin emas hadiah quest!",
                    "Epilog: Pesta Barbeque Kemenangan"
                )

    def _generate_choices_for_beat(self, scene_idx: int, genre: str) -> List[StoryChoice]:
        return [
            StoryChoice(
                id="opt_1",
                label="Serangan Terkoordinasi Penuh Gaya!",
                description="Gunakan seluruh kekuatan fisik dan senjata guild untuk mendobrak rintangan.",
                dc_check=11 + scene_idx,
                stat_affinity="Strength",
                hp_impact=-5,
                morale_impact=15,
                gold_impact=25,
                item_reward=f"Item Antik Babak {scene_idx}",
                consequence_text="Serangan telak kalian berhasil memporak-porandakan barisan musuh!"
            ),
            StoryChoice(
                id="opt_2",
                label="Gunakan Sihir & Trik Akal-Akalan Eve",
                description="Kombinasikan mantra ilusi Eve dan jebakan cerdik buatan chat.",
                dc_check=12 + scene_idx,
                stat_affinity="Magic",
                hp_impact=0,
                morale_impact=20,
                gold_impact=30,
                item_reward="Batu Permata Sihir",
                consequence_text="Trik sulap dan ilusi mengecoh musuh mentah-mentah!"
            ),
            StoryChoice(
                id="opt_3",
                label="Negosiasi & Rayuan Diplomasi Absurd",
                description="Ajak musuh berbicara baik-baik, sogok dengan martabak atau donasi.",
                dc_check=10 + scene_idx,
                stat_affinity="Charisma",
                hp_impact=15,
                morale_impact=10,
                gold_impact=-10,
                item_reward="Surat Aliansi Perdamaian",
                consequence_text="Musuh terenyuh mendengar kata-kata manis kalian dan memilih berdamai!"
            )
        ]

    # --- Campaign Conclusion ---
    def end_campaign(self, outcome_summary: Optional[str] = None) -> Tuple[CampaignSession, str]:
        """Concludes the active campaign, archives it, and creates persistent episodic memory."""
        self.session.status = CampaignStatus.COMPLETED.value
        self.session.total_episodes_completed += 1

        summary = outcome_summary or (
            f"Guild Chat & Eve sukses menyelesaikan petualangan '{self.session.title}' "
            f"dengan sisa darah {self.session.party.hp} HP dan perolehan {self.session.party.gold} koin emas!"
        )

        # Store key memory
        memory_entry = f"Campaign '{self.session.title}': {summary}"
        if memory_entry not in self.session.key_memories:
            self.session.key_memories.append(memory_entry)

        # Archive to history
        archive_item = {
            "id": self.session.id,
            "title": self.session.title,
            "genre": self.session.genre,
            "eve_role": self.session.eve_role,
            "total_scenes": len(self.session.scenes_history),
            "final_hp": self.session.party.hp,
            "final_gold": self.session.party.gold,
            "summary": summary,
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.campaigns_history.insert(0, archive_item)

        speech = (
            f"[emotion: happy] PETUALANGAN SELESAI! 🎉 Terima kasih seluruh anggota Guild Chat tercinta! "
            f"{summary} Petualangan epik ini bakal selamanya tercatat di buku sejarah Second Brain kita! [action: wink]"
        )

        self.save()
        self.sync_to_second_brain()
        return self.session, speech

    # --- Second Brain Markdown Sync ---
    def sync_to_second_brain(self):
        try:
            m_dir = self.second_brain_dir / "storytelling"
            m_dir.mkdir(parents=True, exist_ok=True)
            f_path = m_dir / "campaigns.md"

            lines = [
                "# 📖 Dynamic Storytelling & Community Roleplay Chronicles",
                f"> Last synchronized: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## 🎭 Active Roleplay Campaign",
                f"- **Title**: `{self.session.title}`",
                f"- **Genre**: `{self.session.genre.replace('_', ' ').title()}`",
                f"- **Eve's Role**: `{self.session.eve_role.replace('_', ' ').title()}`",
                f"- **Status**: `{self.session.status.upper()}`",
                f"- **Party HP**: {self.session.party.hp}/{self.session.party.max_hp} | **Morale**: {self.session.party.morale}% | **Gold**: {self.session.party.gold}G",
                f"- **Current Location**: `{self.session.party.current_location}`",
                f"- **Party Inventory**: {', '.join(self.session.party.inventory) if self.session.party.inventory else 'Empty'}",
                "",
                "### 📜 Current Scene",
            ]

            if self.session.current_scene:
                lines.append(f"**{self.session.current_scene.title}**")
                lines.append(f"> \"{self.session.current_scene.narrative}\"")
                lines.append("")
                lines.append("**Pilihan Tindakan Aktif:**")
                for c in self.session.current_scene.choices:
                    lines.append(f"- **[{c.id.upper()}] {c.label}**: {c.description} *(Votes: {len(c.votes)})*")
            else:
                lines.append("*Belum ada adegan aktif.*")

            lines.append("")
            lines.append("## 🧠 Persistent Episodic Lore & Memories")
            for m in self.session.key_memories[-8:]:
                lines.append(f"- 📜 {m}")

            lines.append("")
            lines.append("## 🏆 Campaign History & Archives")
            lines.append("| Title | Genre | Final HP | Gold | Date | Summary |")
            lines.append("|:------|:-----:|:--------:|:----:|:----:|:--------|")
            for h in self.campaigns_history[:8]:
                lines.append(
                    f"| **{h.get('title', 'Unknown')}** | `{h.get('genre', 'rpg')}` | {h.get('final_hp', '-')} HP | "
                    f"{h.get('final_gold', '-')}G | {h.get('completed_at', '-')} | {h.get('summary', '')} |"
                )

            f_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"[StoryEngine] Error syncing Second Brain campaigns: {e}")

    # --- System Prompt Directive ---
    def get_prompt_directive(self) -> str:
        if self.session.status == CampaignStatus.IDLE.value:
            lore_hints = "; ".join(self.session.key_memories[-2:]) if self.session.key_memories else "None"
            return (
                "[📖 DYNAMIC STORYTELLING & ROLEPLAY DIRECTIVE]\n"
                "Campaign Status: IDLE (No active story campaign).\n"
                f"Past Campaign Lore: {lore_hints}\n"
                "You can invite chat to start an interactive RPG adventure anytime: Fantasy, Cyberpunk Heist, or Minecraft Quest!"
            )

        sc = self.session.current_scene
        sc_title = sc.title if sc else "Unknown"
        sc_text = sc.narrative if sc else ""
        choices_text = ", ".join([f"'{c.label}' ({len(c.votes)} votes)" for c in sc.choices]) if sc else ""

        return (
            f"[📖 LIVE INTERACTIVE RPG & ROLEPLAY CAMPAIGN: {self.session.title.upper()}]\n"
            f"You are actively roleplaying in an interactive community RPG adventure!\n"
            f"- Your Role: {self.session.eve_role.replace('_', ' ').title()}\n"
            f"- Genre: {self.session.genre.replace('_', ' ').title()}\n"
            f"- Current Location: {self.session.party.current_location}\n"
            f"- Party Status: {self.session.party.hp}/100 HP, Morale {self.session.party.morale}%, Gold {self.session.party.gold}G\n"
            f"- Active Scene: \"{sc_title}\"\n"
            f"- Scene Narrative: \"{sc_text}\"\n"
            f"- Choices on Table: {choices_text}\n\n"
            "ROLEPLAY DIRECTIVES:\n"
            "1. Speak COMPLETELY in character according to your assigned role (e.g. Tsundere Mage, Snarky Rogue, or DM)!\n"
            "2. Hype up community choices and react with emotion tags [emotion: ...] to party HP, danger, and dice rolls.\n"
            "3. If chat rolls a D20, react dramatically to Nat 20 (legendary joy) or Nat 1 (hilarious blunder).\n"
            "4. Acknowledge that the chat viewers are your adventuring guild companions."
        )

    # --- Unified State ---
    def get_state(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "campaigns_history": self.campaigns_history[:8],
            "total_campaigns_completed": len(self.campaigns_history),
            "presets": [
                {
                    "key": k,
                    "title": v["title"],
                    "genre": v["genre"],
                    "role": v["default_role"],
                    "description": v["description"]
                }
                for k, v in PRESET_CAMPAIGNS.items()
            ]
        }
