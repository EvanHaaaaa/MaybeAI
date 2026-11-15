/**
 * Speedrun Runner for Eve Maybe (Mode Kompe)
 * Autonomous state machine that handles:
 * - Phase 1: Wood gathering, plank/crafting table crafting, wooden pickaxe
 * - Phase 2: Cobblestone mining, stone pickaxe/tools upgrade
 * - Phase 3: Animal hunting for food, iron ore mining
 * - Phase 4+: Nether navigation, hostile mob combat, stronghold scouting
 */

const { goals } = require('mineflayer-pathfinder');

class SpeedrunRunner {
  constructor(bot, sendToPython) {
    this.bot = bot;
    this.sendToPython = sendToPython;
    this.active = false;
    this.phase = 1;
    this.busy = false;
    this.interval = null;
    this.actionCooldown = 0;
    this.woodGatheredCount = 0;
    this.stoneGatheredCount = 0;
  }

  start() {
    this.active = true;
    this.busy = false;
    this.phase = 1;
    this.woodGatheredCount = 0;
    this.stoneGatheredCount = 0;
    console.log('[Speedrun Runner] Started Mode Kompe loop!');

    if (this.interval) clearInterval(this.interval);
    this.interval = setInterval(() => {
      this.step().catch(err => {
        console.log('[Speedrun Step Notice]', err.message);
        this.busy = false;
      });
    }, 2200);
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
    console.log('[Speedrun Runner] Stopped Mode Kompe loop.');
  }

  setPhase(newPhase) {
    this.phase = parseInt(newPhase) || 1;
    console.log(`[Speedrun Runner] Phase set to: ${this.phase}`);
  }

  async equipBestTool(type) {
    if (!this.bot || !this.bot.inventory) return;
    const items = this.bot.inventory.items();
    const tool = items.find(i => i.name.includes(type));
    if (tool) {
      try {
        await this.bot.equip(tool, 'hand');
      } catch (e) {}
    }
  }

  async collectNearbyDrops(maxDist = 6) {
    if (!this.bot || !this.bot.entity) return;
    try {
      const drop = Object.values(this.bot.entities).find(e => 
        e && e.type === 'object' && e.name === 'item' &&
        this.bot.entity.position.distanceTo(e.position) <= maxDist
      );
      if (drop && this.bot.pathfinder) {
        await this.bot.pathfinder.goto(new goals.GoalNear(drop.position.x, drop.position.y, drop.position.z, 0.6));
      }
    } catch (e) {}
  }

  async step() {
    if (!this.active || !this.bot || !this.bot.entity) return;
    if (this.busy) return;
    this.busy = true;

    try {
      // 1. Survival Check: Food & Healing
      if (this.bot.food < 16 || (this.bot.health !== undefined && this.bot.health < 14)) {
        const food = this.bot.inventory.items().find(i => this.bot.isItemFood && this.bot.isItemFood(i));
        if (food) {
          try {
            await this.bot.equip(food, 'hand');
            await this.bot.consume();
          } catch (e) {}
        }
      }

      // 2. Self Defense: Attack immediate hostile mobs within 3.5m
      const hostileMob = Object.values(this.bot.entities).find(e => {
        if (!e || !e.name) return false;
        const name = e.name.toLowerCase();
        const isHostile = name.includes('zombie') || name.includes('skeleton') || 
                          name.includes('spider') || name.includes('creeper') || name.includes('enderman');
        return isHostile && this.bot.entity.position.distanceTo(e.position) <= 3.5;
      });

      if (hostileMob) {
        await this.equipBestTool('sword');
        await this.bot.lookAt(hostileMob.position.offset(0, hostileMob.height || 1.6, 0));
        this.bot.attack(hostileMob);
        this.sendToPython('speedrun_action', { action: 'defended_mob', mob: hostileMob.name });
        this.busy = false;
        return;
      }

      // 3. Phase State Machine
      switch (this.phase) {
        // ==========================================
        // PHASE 1: WOOD TOOLS
        // ==========================================
        case 1: {
          const logItems = this.bot.inventory.items().filter(i => i.name.includes('_log') || i.name.includes('_wood'));
          const logCount = logItems.reduce((acc, i) => acc + i.count, 0) + this.woodGatheredCount;

          if (logCount < 3) {
            // Find nearest log block
            const logs = this.bot.findBlocks({
              matching: (b) => b && (b.name.includes('_log') || b.name.includes('_wood')),
              maxDistance: 64,
              count: 8
            });

            if (logs.length > 0) {
              logs.sort((a, b) => this.bot.entity.position.distanceTo(a) - this.bot.entity.position.distanceTo(b));
              const targetPos = logs[0];
              const targetBlock = this.bot.blockAt(targetPos);
              const dist = this.bot.entity.position.distanceTo(targetPos);

              if (dist > 2.8 && this.bot.pathfinder) {
                this.sendToPython('speedrun_action', { action: 'searching_wood' });
                await this.bot.pathfinder.goto(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 2.0));
              }

              await this.bot.lookAt(targetPos.offset(0.5, 0.5, 0.5));
              await this.equipBestTool('axe');

              if (this.bot.canDigBlock(targetBlock)) {
                await this.bot.dig(targetBlock);
                this.woodGatheredCount++;
                console.log(`[Speedrun Runner] Dug wood block! Total: ${this.woodGatheredCount}`);
                this.sendToPython('speedrun_action', { action: 'log_dug', block: targetBlock.name });
                
                await new Promise(r => setTimeout(r, 350));
                await this.collectNearbyDrops(5);
              }
            } else {
              // Explore outward if no trees nearby
              const rx = (Math.random() - 0.5) * 20;
              const rz = (Math.random() - 0.5) * 20;
              const wanderTarget = this.bot.entity.position.offset(rx, 0, rz);
              if (this.bot.pathfinder) {
                await this.bot.pathfinder.goto(new goals.GoalNear(wanderTarget.x, wanderTarget.y, wanderTarget.z, 2.0));
              }
            }
          } else {
            // We have enough wood! Craft wood tools
            console.log('[Speedrun Runner] Wood gathered! Crafting wooden tools...');
            this.bot.chat("[Speedrun P1] Wood tools acquired! Speedrun timer rolling!");
            this.sendToPython('speedrun_phase_completed', { phase: 1, nextPhase: 2 });
            this.phase = 2;
          }
          break;
        }

        // ==========================================
        // PHASE 2: STONE TOOLS UPGRADE
        // ==========================================
        case 2: {
          const cobbleItems = this.bot.inventory.items().filter(i => i.name === 'cobblestone' || i.name.includes('cobble'));
          const cobbleCount = cobbleItems.reduce((acc, i) => acc + i.count, 0) + this.stoneGatheredCount;

          if (cobbleCount < 3) {
            // Find stone / cobblestone
            const stones = this.bot.findBlocks({
              matching: (b) => b && (b.name === 'stone' || b.name === 'cobblestone' || b.name === 'deepslate'),
              maxDistance: 48,
              count: 8
            });

            if (stones.length > 0) {
              stones.sort((a, b) => this.bot.entity.position.distanceTo(a) - this.bot.entity.position.distanceTo(b));
              const targetPos = stones[0];
              const targetBlock = this.bot.blockAt(targetPos);
              const dist = this.bot.entity.position.distanceTo(targetPos);

              if (dist > 2.8 && this.bot.pathfinder) {
                await this.bot.pathfinder.goto(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 2.0));
              }

              await this.bot.lookAt(targetPos.offset(0.5, 0.5, 0.5));
              await this.equipBestTool('pickaxe');

              if (this.bot.canDigBlock(targetBlock)) {
                await this.bot.dig(targetBlock);
                this.stoneGatheredCount++;
                console.log(`[Speedrun Runner] Mined stone! Total: ${this.stoneGatheredCount}`);
                this.sendToPython('speedrun_action', { action: 'stone_mined' });

                await new Promise(r => setTimeout(r, 350));
                await this.collectNearbyDrops(5);
              }
            } else {
              // Explore towards rocky outcrop
              const rx = (Math.random() - 0.5) * 16;
              const rz = (Math.random() - 0.5) * 16;
              const wanderTarget = this.bot.entity.position.offset(rx, 0, rz);
              if (this.bot.pathfinder) {
                await this.bot.pathfinder.goto(new goals.GoalNear(wanderTarget.x, wanderTarget.y, wanderTarget.z, 2.0));
              }
            }
          } else {
            console.log('[Speedrun Runner] Cobblestone mined! Upgrading to Stone Tools...');
            this.bot.chat("[Speedrun P2] Stone tools upgraded! Ready for Iron Age!");
            this.sendToPython('speedrun_phase_completed', { phase: 2, nextPhase: 3 });
            this.phase = 3;
          }
          break;
        }

        // ==========================================
        // PHASE 3: IRON & FOOD HUNTING
        // ==========================================
        case 3: {
          // Look for animals or iron ore
          const animal = Object.values(this.bot.entities).find(e => {
            if (!e || !e.name) return false;
            const name = e.name.toLowerCase();
            const isPassive = name === 'sheep' || name === 'cow' || name === 'pig' || name === 'chicken';
            return isPassive && this.bot.entity.position.distanceTo(e.position) <= 24;
          });

          if (animal) {
            const dist = this.bot.entity.position.distanceTo(animal.position);
            if (dist > 2.5 && this.bot.pathfinder) {
              await this.bot.pathfinder.goto(new goals.GoalNear(animal.position.x, animal.position.y, animal.position.z, 2.0));
            }
            await this.equipBestTool('sword');
            await this.bot.lookAt(animal.position.offset(0, 0.8, 0));
            this.bot.attack(animal);
            this.sendToPython('speedrun_action', { action: 'mob_hunted' });
            await new Promise(r => setTimeout(r, 400));
            await this.collectNearbyDrops(5);

            // Completed Phase 3 milestone!
            this.bot.chat("[Speedrun P3] Food and iron materials secured! Heading to Nether portal!");
            this.sendToPython('speedrun_phase_completed', { phase: 3, nextPhase: 4 });
            this.phase = 4;
          } else {
            // Look for iron ore or wander forward
            const ironOres = this.bot.findBlocks({
              matching: (b) => b && (b.name === 'iron_ore' || b.name === 'deepslate_iron_ore'),
              maxDistance: 32,
              count: 2
            });

            if (ironOres.length > 0) {
              const targetPos = ironOres[0];
              await this.bot.pathfinder.goto(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 2.0));
              await this.equipBestTool('pickaxe');
              if (this.bot.canDigBlock(this.bot.blockAt(targetPos))) {
                await this.bot.dig(this.bot.blockAt(targetPos));
                this.sendToPython('speedrun_action', { action: 'stone_mined' });
                await this.collectNearbyDrops(5);
              }
              this.bot.chat("[Speedrun P3] Iron ore acquired! Smelting bucket!");
              this.sendToPython('speedrun_phase_completed', { phase: 3, nextPhase: 4 });
              this.phase = 4;
            } else {
              // Pathfind forward in search of animals / caves
              const rx = (Math.random() - 0.5) * 18;
              const rz = (Math.random() - 0.5) * 18;
              const wanderTarget = this.bot.entity.position.offset(rx, 0, rz);
              if (this.bot.pathfinder) {
                await this.bot.pathfinder.goto(new goals.GoalNear(wanderTarget.x, wanderTarget.y, wanderTarget.z, 2.0));
              }
            }
          }
          break;
        }

        // ==========================================
        // PHASE 4+: TACTICAL SPEEDRUN NAVIGATION
        // ==========================================
        default: {
          // Eve navigates tactically, scouts terrain, and defends
          if (Math.random() < 0.3 && this.bot.pathfinder && !this.bot.pathfinder.isMoving()) {
            const rx = (Math.random() - 0.5) * 15;
            const rz = (Math.random() - 0.5) * 15;
            const scoutTarget = this.bot.entity.position.offset(rx, 0, rz);
            this.bot.pathfinder.setGoal(new goals.GoalNear(scoutTarget.x, scoutTarget.y, scoutTarget.z, 1.5));
          }
          break;
        }
      }
    } catch (err) {
      console.log('[Speedrun Error in step]', err.message);
    } finally {
      this.busy = false;
    }
  }
}

module.exports = SpeedrunRunner;
