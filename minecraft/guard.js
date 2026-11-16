/**
 * Guard Runner for Eve Maybe (Mode Guard / Bodyguard Player)
 * 
 * Provides vigilant bodyguard capabilities for Eve in Minecraft:
 * - Shadows and stays close to a designated player (or nearest player if none specified)
 * - Constantly scans for hostile mob threats in a 14-block radius
 * - Automatically intercepts and attacks hostile mobs threatening the player
 * - Tactical awareness: special hit-and-retreat maneuver against Creepers
 * - Immediate counter-attack if the guarded player is struck by an entity
 * - Alerts player and stream chat via WebSocket bridge with cute & sassy bodyguard reactions
 */

const { goals } = require('mineflayer-pathfinder');

const HOSTILE_MOBS = new Set([
  'zombie', 'skeleton', 'spider', 'creeper', 'enderman', 'phantom',
  'witch', 'drowned', 'husk', 'stray', 'silverfish', 'cave_spider',
  'slime', 'magma_cube', 'pillager', 'vindicator', 'ravager', 'evoker',
  'vex', 'hoglin', 'piglin_brute', 'blaze', 'ghast', 'wither_skeleton',
  'guardian', 'elder_guardian', 'warden'
]);

class GuardRunner {
  constructor(bot, sendToPython) {
    this.bot = bot;
    this.sendToPython = sendToPython;
    this.active = false;
    this.targetPlayerName = null;
    this.guardRadius = 3.5;
    this.scanRadius = 14;
    this.interval = null;
    this.busy = false;
    this.combatTarget = null;
    this.lastAttackedMobId = null;
    this.lastThreatAlertTime = 0;
    this.lastAttackTime = 0;
    this.creeperCooldown = false;
  }

  setTarget(playerName) {
    this.targetPlayerName = playerName || null;
    console.log(`[Guard Runner] Guard target updated to: ${this.targetPlayerName || 'Nearest Player'}`);
  }

  start(playerName) {
    this.active = true;
    this.busy = false;
    this.combatTarget = null;
    if (playerName) this.targetPlayerName = playerName;

    console.log(`[Guard Runner] Mode Guard started! Target: ${this.targetPlayerName || 'Nearest Player'}`);

    if (this.interval) clearInterval(this.interval);
    this.interval = setInterval(() => {
      this.step().catch(err => {
        console.log('[Guard Step Notice]', err.message);
        this.busy = false;
      });
    }, 1200);

    // Initial announcement
    this.sendToPython('guard_started', {
      target: this.targetPlayerName || 'Nearest Player'
    });
  }

  stop() {
    this.active = false;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.busy = false;
    this.combatTarget = null;
    if (this.bot && this.bot.pathfinder) {
      try { this.bot.pathfinder.setGoal(null); } catch (e) {}
    }
    console.log('[Guard Runner] Mode Guard stopped.');
  }

  getTargetPlayerEntity() {
    if (!this.bot || !this.bot.entity) return null;

    // 1. If explicit player name is set
    if (this.targetPlayerName) {
      const p = this.bot.players[this.targetPlayerName];
      if (p && p.entity) return { player: p, entity: p.entity, name: this.targetPlayerName };
    }

    // 2. Otherwise find nearest non-bot player
    let nearest = null;
    let minDist = 32;
    for (const name in this.bot.players) {
      if (name.toLowerCase() === this.bot.username.toLowerCase()) continue;
      const player = this.bot.players[name];
      if (player && player.entity) {
        const dist = this.bot.entity.position.distanceTo(player.entity.position);
        if (dist < minDist) {
          minDist = dist;
          nearest = { player: player, entity: player.entity, name: name };
        }
      }
    }
    return nearest;
  }

  async equipBestWeapon() {
    if (!this.bot || !this.bot.inventory) return;
    const items = this.bot.inventory.items();
    if (items.length === 0) return;

    const weaponOrder = [
      'netherite_sword', 'diamond_sword', 'iron_sword', 'golden_sword', 'stone_sword', 'wooden_sword',
      'netherite_axe', 'diamond_axe', 'iron_axe', 'golden_axe', 'stone_axe', 'wooden_axe',
      'trident', 'bow', 'crossbow'
    ];

    let bestWeapon = null;
    for (const name of weaponOrder) {
      const it = items.find(i => i && i.name === name);
      if (it) {
        bestWeapon = it;
        break;
      }
    }

    if (!bestWeapon) {
      bestWeapon = items.find(i => i && (i.name.includes('sword') || i.name.includes('axe')));
    }

    if (bestWeapon) {
      try {
        await this.bot.equip(bestWeapon, 'hand');
      } catch (e) {}
    }

    // Off-hand shield
    const shield = items.find(i => i && i.name === 'shield');
    if (shield) {
      try {
        await this.bot.equip(shield, 'off-hand');
      } catch (e) {}
    }
  }

  findNearbyThreats(guardedEntity) {
    if (!this.bot || !this.bot.entity) return [];
    const threats = [];
    const basePos = guardedEntity ? guardedEntity.position : this.bot.entity.position;

    for (const id in this.bot.entities) {
      const e = this.bot.entities[id];
      if (!e || !e.name) continue;

      const mobName = e.name.toLowerCase();
      if (!HOSTILE_MOBS.has(mobName)) continue;

      // Distance to guarded player or Eve
      const distToPlayer = guardedEntity ? basePos.distanceTo(e.position) : 999;
      const distToEve = this.bot.entity.position.distanceTo(e.position);
      const effectiveDist = Math.min(distToPlayer, distToEve);

      if (effectiveDist <= this.scanRadius) {
        threats.push({
          entity: e,
          name: e.name,
          distance: effectiveDist,
          isCreeper: mobName === 'creeper'
        });
      }
    }

    // Sort by proximity (closest threats first)
    threats.sort((a, b) => a.distance - b.distance);
    return threats;
  }

  onGuardedPlayerHurt(attackerEntity, targetName) {
    if (!this.active || !attackerEntity) return;
    console.log(`[Guard Runner] Guarded player ${targetName} was hurt by ${attackerEntity.name || 'entity'}! Counter-attacking!`);
    this.combatTarget = attackerEntity;
    this.sendToPython('guard_player_hurt', {
      attacker: attackerEntity.name || 'hostile',
      target: targetName
    });
  }

  async engageMob(threat, guardedName) {
    if (!this.bot || !threat || !threat.entity) return;
    const mob = threat.entity;
    const now = Date.now();

    // Broadcast threat detection (throttle to once per 5 seconds)
    if (now - this.lastThreatAlertTime > 5000) {
      this.lastThreatAlertTime = now;
      this.sendToPython('guard_threat_detected', {
        mob: threat.name,
        distance: Math.round(threat.distance * 10) / 10,
        targetPlayer: guardedName || 'Player',
        isCreeper: threat.isCreeper
      });

      if (threat.isCreeper) {
        this.bot.chat(`Awas ada Creeper di dekatmu, ${guardedName}! Mundur, biar aku atasi! 💥`);
      }
    }

    await this.equipBestWeapon();

    const distToMob = this.bot.entity.position.distanceTo(mob.position);

    // Look at the mob
    try {
      this.bot.lookAt(mob.position.offset(0, mob.height ? mob.height * 0.8 : 1.2, 0), true);
    } catch (e) {}

    // Special tactical retreat against Creepers to prevent detonation
    if (threat.isCreeper && distToMob <= 3.2 && !this.creeperCooldown) {
      this.creeperCooldown = true;
      try {
        this.bot.attack(mob);
        this.bot.setControlState('back', true);
        this.bot.setControlState('jump', true);
        setTimeout(() => {
          if (this.bot) {
            this.bot.setControlState('back', false);
            this.bot.setControlState('jump', false);
          }
          this.creeperCooldown = false;
        }, 600);
      } catch (e) {}
      return;
    }

    // Standard attack
    if (distToMob <= 3.2) {
      try {
        this.bot.attack(mob);
        this.lastAttackTime = now;
        this.lastAttackedMobId = mob.id;
      } catch (e) {}
    } else if (this.bot.pathfinder) {
      // Close distance
      try {
        this.bot.pathfinder.setGoal(new goals.GoalFollow(mob, 2.0), false);
      } catch (e) {}
    }
  }

  async step() {
    if (!this.active || this.busy || !this.bot || !this.bot.entity) return;
    this.busy = true;

    try {
      const guarded = this.getTargetPlayerEntity();

      // Check current combat target status
      if (this.combatTarget) {
        const stillExists = this.bot.entities[this.combatTarget.id];
        if (!stillExists || !stillExists.isValid) {
          console.log(`[Guard Runner] Threat ${this.combatTarget.name || 'mob'} eliminated!`);
          this.sendToPython('guard_mob_eliminated', {
            mob: this.combatTarget.name || 'hostile',
            targetPlayer: guarded ? guarded.name : 'Player'
          });
          this.combatTarget = null;
        }
      }

      // Scan for threats around guarded player or Eve
      const threats = this.findNearbyThreats(guarded ? guarded.entity : null);

      if (threats.length > 0) {
        const primaryThreat = threats[0];
        this.combatTarget = primaryThreat.entity;
        await this.engageMob(primaryThreat, guarded ? guarded.name : 'Player');
        this.busy = false;
        return;
      }

      // No active threats: return/stay close to guarded player
      if (guarded && guarded.entity) {
        const distToPlayer = this.bot.entity.position.distanceTo(guarded.entity.position);

        if (distToPlayer > this.guardRadius) {
          // Follow player
          if (this.bot.pathfinder) {
            this.bot.pathfinder.setGoal(new goals.GoalFollow(guarded.entity, 2.5), true);
          }
        } else {
          // Close enough: look vigilant, track surroundings or face player
          if (this.bot.pathfinder && this.bot.pathfinder.isMoving()) {
            this.bot.pathfinder.setGoal(null);
          }
          // Face guarded player or look outwards defensively
          if (Math.random() < 0.6) {
            this.bot.lookAt(guarded.entity.position.offset(0, 1.5, 0));
          } else {
            const scanAngle = this.bot.entity.yaw + (Math.random() - 0.5) * 1.8;
            this.bot.look(scanAngle, 0.1, false);
          }
        }
      } else {
        // No player found in range, stand by defensively
        if (Math.random() < 0.2) {
          const scanAngle = this.bot.entity.yaw + (Math.random() - 0.5) * 1.5;
          this.bot.look(scanAngle, 0, false);
        }
      }

    } catch (err) {
      console.log('[Guard Step Error]', err.message);
    } finally {
      this.busy = false;
    }
  }
}

module.exports = GuardRunner;
