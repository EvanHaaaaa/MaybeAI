/**
 * Casual Runner for Eve Maybe (Mode Santai)
 * Handles autonomous, lively player behavior in casual mode:
 * - Actively seeks out and approaches other players on the server
 * - Social greetings, waving arm, friendly crouching/jumping
 * - Gathers items & materials (picking flowers, harvesting mature crops, collecting drops)
 * - Observes and interacts with passive animals (cows, sheep, pigs, chickens)
 * - Natural exploration of terrain and scenic vantage points
 */

const { goals } = require('mineflayer-pathfinder');

class CasualRunner {
  constructor(bot, sendToPython) {
    this.bot = bot;
    this.sendToPython = sendToPython;
    this.active = false;
    this.busy = false;
    this.interval = null;
    this.greetedPlayers = new Set();
    this.lastGiftTimes = new Map();
    this.actionCooldown = 0;
    this.lastActionTime = 0;
  }

  start() {
    this.active = true;
    this.busy = false;
    console.log('[Casual Runner] Mode Santai active & wandering initialized!');

    if (this.interval) clearInterval(this.interval);
    this.interval = setInterval(() => {
      this.step().catch(err => {
        console.log('[Casual Step Notice]', err.message);
        this.busy = false;
      });
    }, 2500);
  }

  stop() {
    this.active = false;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.busy = false;
    if (this.bot && this.bot.pathfinder) {
      try { this.bot.pathfinder.setGoal(null); } catch (e) {}
    }
    console.log('[Casual Runner] Mode Santai stopped.');
  }

  getNearestOtherPlayer(maxDist = 40) {
    if (!this.bot || !this.bot.entity) return null;
    let nearest = null;
    let minDist = maxDist;

    for (const name in this.bot.players) {
      if (name.toLowerCase() === this.bot.username.toLowerCase()) continue;
      const player = this.bot.players[name];
      if (player && player.entity) {
        const dist = this.bot.entity.position.distanceTo(player.entity.position);
        if (dist < minDist) {
          minDist = dist;
          nearest = { player: player, entity: player.entity, distance: dist };
        }
      }
    }
    return nearest;
  }

  async collectNearbyDrops(maxDist = 12) {
    if (!this.bot || !this.bot.entity) return false;
    try {
      const drop = Object.values(this.bot.entities).find(e => 
        e && e.type === 'object' && e.name === 'item' &&
        this.bot.entity.position.distanceTo(e.position) <= maxDist
      );
      if (drop && this.bot.pathfinder) {
        console.log(`[Casual Runner] Picking up dropped item at ${drop.position}`);
        await this.bot.pathfinder.goto(new goals.GoalNear(drop.position.x, drop.position.y, drop.position.z, 0.6));
        this.sendToPython('casual_action', { action: 'picked_item' });
        return true;
      }
    } catch (e) {}
    return false;
  }

  findNearbyFlower(maxDist = 16) {
    if (!this.bot || !this.bot.entity) return null;
    const flowerNames = [
      'dandelion', 'poppy', 'blue_orchid', 'allium', 'azure_bluet',
      'red_tulip', 'orange_tulip', 'white_tulip', 'pink_tulip',
      'oxeye_daisy', 'cornflower', 'lily_of_the_valley', 'sunflower'
    ];
    const positions = this.bot.findBlocks({
      matching: (b) => b && flowerNames.some(f => b.name.includes(f)),
      maxDistance: maxDist,
      count: 3
    });
    return positions.length > 0 ? positions[0] : null;
  }

  findNearbyAnimal(maxDist = 16) {
    if (!this.bot || !this.bot.entity) return null;
    const passiveAnimals = ['sheep', 'cow', 'pig', 'chicken', 'horse', 'rabbit', 'cat'];
    return Object.values(this.bot.entities).find(e => {
      if (!e || !e.name) return false;
      const isPassive = passiveAnimals.includes(e.name.toLowerCase());
      return isPassive && this.bot.entity.position.distanceTo(e.position) <= maxDist;
    });
  }

  async giftPlayer(player, entity) {
    if (!this.bot || !this.bot.inventory) return false;
    const items = this.bot.inventory.items();
    if (items.length === 0) return false;

    // Prioritize sweet/cute items: flowers, food, seeds, shiny minerals
    const sweetPriorities = [
      'flower', 'poppy', 'dandelion', 'tulip', 'orchid', 'sunflower', 'daisy',
      'apple', 'bread', 'cookie', 'berries', 'carrot',
      'diamond', 'emerald', 'gold', 'amethyst', 'seed'
    ];

    let giftItem = items.find(i => sweetPriorities.some(p => i.name.toLowerCase().includes(p)));
    if (!giftItem) {
      giftItem = items[Math.floor(Math.random() * items.length)];
    }

    try {
      console.log(`[Casual Runner] Gifting ${giftItem.name} to player ${player.username}`);
      await this.bot.lookAt(entity.position.offset(0, 1.2, 0));
      await this.bot.toss(giftItem.type, null, 1);

      // Sweet reaction gestures: crouch & wave
      this.bot.setControlState('sneak', true);
      setTimeout(() => this.bot.setControlState('sneak', false), 600);
      try { this.bot.swingArm('right'); } catch (e) {}

      const cleanItemName = giftItem.name.replace(/_/g, ' ');
      const giftMessages = [
        `Ini buat kamu, ${player.username}! Hadiah spesial dari aku~ ✨`,
        `Aku nemu ${cleanItemName} tadi, ini buat kamu ${player.username}! Simpan baik-baik ya 🎁`,
        `Nih hadiah kecil buat kamu ${player.username}, dijaga baik-baik yaa! 💕`
      ];
      const chatMsg = giftMessages[Math.floor(Math.random() * giftMessages.length)];
      this.bot.chat(chatMsg);

      this.sendToPython('casual_action', {
        action: 'gifted_player',
        player: player.username,
        item: cleanItemName
      });
      return true;
    } catch (e) {
      console.log('[Casual Runner Gifting Notice]', e.message);
      return false;
    }
  }

  async step() {
    if (!this.active || !this.bot || !this.bot.entity) return;
    if (this.busy) return;
    this.busy = true;

    try {
      // 1. Priority: Cari & Interaksi dengan Player Lain di Server
      const nearestPlayerData = this.getNearestOtherPlayer(40);
      if (nearestPlayerData) {
        const { player, entity, distance } = nearestPlayerData;

        // Player berjarak sedang (4 - 40 blok): hampiri player
        if (distance > 3.5) {
          if (this.bot.pathfinder && !this.bot.pathfinder.isMoving()) {
            console.log(`[Casual Runner] Approaching player ${player.username} (${distance.toFixed(1)}m away)`);
            this.bot.pathfinder.setGoal(new goals.GoalNear(entity.position.x, entity.position.y, entity.position.z, 3.0));
          }
          this.busy = false;
          return;
        }

        // Sudah dekat dengan player (<= 3.5 blok): lakukan interaksi sosial
        this.bot.pathfinder.setGoal(null);
        await this.bot.lookAt(entity.position.offset(0, 1.6, 0));

        // Friendly gesture: sneak peek / crouch & wave arm
        if (Math.random() < 0.4) {
          this.bot.setControlState('sneak', true);
          setTimeout(() => this.bot.setControlState('sneak', false), 500);
          try { this.bot.swingArm('right'); } catch (e) {}
        }

        // Greet player in chat jika belum disapa
        if (!this.greetedPlayers.has(player.username)) {
          this.greetedPlayers.add(player.username);
          const greetings = [
            `Halo ${player.username}! Senang ketemu kamu di sini! ✨`,
            `Hai ${player.username}! Lagi sibuk bikin apa nih? 😄`,
            `Haii ${player.username}! Mau jalan-jalan bareng aku?`
          ];
          const greetMsg = greetings[Math.floor(Math.random() * greetings.length)];
          this.bot.chat(greetMsg);
          this.sendToPython('player_nearby', { username: player.username, distance: distance });
        }

        // --- Sweet Gifting Gesture ---
        // Hadiahkan barang acak dari inventory ke player (cooldown 20 detik per player)
        const now = Date.now();
        const lastGift = this.lastGiftTimes.get(player.username) || 0;
        if (now - lastGift > 20000) {
          const gifted = await this.giftPlayer(player, entity);
          if (gifted) {
            this.lastGiftTimes.set(player.username, now);
            this.busy = false;
            return;
          }
        }

        this.busy = false;
        return;
      }

      // 2. Cari & Ambil Dropped Items di Sekitar
      const pickedDrop = await this.collectNearbyDrops(12);
      if (pickedDrop) {
        this.busy = false;
        return;
      }

      // 3. Cari Bahan & Kegiatan Wajar Survival (Petik Bunga / Amati Hewan)
      const now = Date.now();
      if (now - this.lastActionTime > 12000) { // Setiap ~12 detik
        // Coba petik bunga terdekat
        const flowerPos = this.findNearbyFlower(16);
        if (flowerPos && this.bot.pathfinder) {
          this.lastActionTime = now;
          const flowerBlock = this.bot.blockAt(flowerPos);
          console.log(`[Casual Runner] Found flower: ${flowerBlock?.name} at ${flowerPos}`);
          await this.bot.pathfinder.goto(new goals.GoalNear(flowerPos.x, flowerPos.y, flowerPos.z, 2.0));
          await this.bot.lookAt(flowerPos.offset(0.5, 0.5, 0.5));
          if (this.bot.canDigBlock(flowerBlock)) {
            await this.bot.dig(flowerBlock);
            await new Promise(r => setTimeout(r, 400));
            await this.collectNearbyDrops(5);
            if (Math.random() < 0.4) {
              this.bot.chat("Nemuin bunga cantik di sini! 🌸");
            }
            this.sendToPython('casual_action', { action: 'picked_flower', flower: flowerBlock.name });
            this.busy = false;
            return;
          }
        }

        // Coba hampiri hewan jinak
        const animal = this.findNearbyAnimal(16);
        if (animal && this.bot.pathfinder) {
          this.lastActionTime = now;
          console.log(`[Casual Runner] Interacting with passive animal: ${animal.name}`);
          await this.bot.pathfinder.goto(new goals.GoalNear(animal.position.x, animal.position.y, animal.position.z, 2.5));
          await this.bot.lookAt(animal.position.offset(0, 0.8, 0));
          if (Math.random() < 0.3) {
            this.bot.chat(`Lucu banget ${animal.name}-nya! 🐾`);
          }
          this.sendToPython('casual_action', { action: 'observed_animal', animal: animal.name });
          this.busy = false;
          return;
        }
      }

      // 4. Natural Exploration (Menjelajah Alam / Scenic Wandering)
      if (this.bot.pathfinder && !this.bot.pathfinder.isMoving()) {
        // Tentukan arah acak agak jauh (14 - 22 blok) agar tidak hanya berputar di satu tempat
        const angle = Math.random() * Math.PI * 2;
        const dist = 14 + Math.random() * 8;
        const targetPos = this.bot.entity.position.offset(
          Math.cos(angle) * dist,
          0,
          Math.sin(angle) * dist
        );

        // Natural head looking
        const lookYaw = this.bot.entity.yaw + (Math.random() - 0.5) * 1.5;
        this.bot.look(lookYaw, 0, false);

        this.bot.pathfinder.setGoal(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 2.0));
      }

    } catch (err) {
      console.log('[Casual Runner Error in step]', err.message);
    } finally {
      this.busy = false;
    }
  }
}

module.exports = CasualRunner;
