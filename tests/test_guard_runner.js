const assert = require('assert');
const GuardRunner = require('../minecraft/guard');

// Mock Mineflayer Bot
const mockBot = {
  username: 'EveMaybe',
  entity: {
    position: {
      x: 0, y: 64, z: 0,
      distanceTo: (pos) => Math.hypot(pos.x - 0, pos.y - 64, pos.z - 0),
      offset: (x, y, z) => ({ x: 0 + x, y: 64 + y, z: 0 + z })
    },
    yaw: 0,
    pitch: 0
  },
  players: {
    EveMaybe: { username: 'EveMaybe' },
    Steve: {
      username: 'Steve',
      entity: {
        position: {
          x: 2, y: 64, z: 2,
          distanceTo: (pos) => Math.hypot(pos.x - 2, pos.y - 64, pos.z - 2),
          offset: (x, y, z) => ({ x: 2 + x, y: 64 + y, z: 2 + z })
        }
      }
    }
  },
  entities: {
    101: {
      id: 101,
      name: 'zombie',
      type: 'mob',
      isValid: true,
      position: { x: 5, y: 64, z: 5 }
    },
    102: {
      id: 102,
      name: 'creeper',
      type: 'mob',
      isValid: true,
      position: { x: 2, y: 64, z: 1 }
    },
    103: {
      id: 103,
      name: 'sheep',
      type: 'mob',
      isValid: true,
      position: { x: 1, y: 64, z: 1 }
    }
  },
  inventory: {
    items: () => [
      { name: 'iron_sword' },
      { name: 'shield' },
      { name: 'bread', count: 10 }
    ]
  },
  equipped: {},
  async equip(item, destination) {
    this.equipped[destination] = item.name;
    return true;
  },
  attack(target) {
    this.attacked = target.name;
  },
  chat(msg) {
    this.lastChat = msg;
  },
  lookAt(pos) {
    this.lastLookAt = pos;
  },
  look(y, p) {},
  setControlState(control, state) {},
  pathfinder: {
    setGoal(goal, dynamic) {
      this.currentGoal = goal;
    },
    isMoving: () => false
  }
};

const bridgeEvents = [];
function sendToPython(type, data) {
  bridgeEvents.push({ type, data });
}

async function runTests() {
  console.log('[Test] Running GuardRunner Unit Tests...');
  const runner = new GuardRunner(mockBot, sendToPython);

  // 1. Test setTarget & start
  runner.start('Steve');
  assert.strictEqual(runner.active, true, 'Runner should be active');
  assert.strictEqual(runner.targetPlayerName, 'Steve', 'Target should be Steve');
  assert.ok(bridgeEvents.some(e => e.type === 'guard_started'), 'guard_started event sent');

  // 2. Test getTargetPlayerEntity
  const targetEntity = runner.getTargetPlayerEntity();
  assert.ok(targetEntity, 'Guarded player entity should be found');
  assert.strictEqual(targetEntity.name, 'Steve');

  // 3. Test findNearbyThreats
  const threats = runner.findNearbyThreats(targetEntity.entity);
  assert.strictEqual(threats.length, 2, 'Should detect zombie and creeper (not sheep)');
  assert.strictEqual(threats[0].name, 'creeper', 'Creeper is closer, should be first');
  assert.strictEqual(threats[0].isCreeper, true, 'Should mark isCreeper as true');

  // 4. Test equipBestWeapon
  await runner.equipBestWeapon();
  assert.strictEqual(mockBot.equipped['hand'], 'iron_sword', 'Equipped iron sword in main hand');
  assert.strictEqual(mockBot.equipped['off-hand'], 'shield', 'Equipped shield in off hand');

  // 5. Test engageMob with Creeper
  await runner.engageMob(threats[0], 'Steve');
  assert.strictEqual(mockBot.attacked, 'creeper', 'Bot should attack creeper');
  assert.ok(mockBot.lastChat.includes('Creeper'), 'Bot should warn in chat about Creeper');

  // 6. Test onGuardedPlayerHurt
  runner.onGuardedPlayerHurt(mockBot.entities[101], 'Steve');
  assert.strictEqual(runner.combatTarget.name, 'zombie', 'Combat target should switch to attacker');
  assert.ok(bridgeEvents.some(e => e.type === 'guard_player_hurt'), 'guard_player_hurt event sent');

  // 7. Stop runner
  runner.stop();
  assert.strictEqual(runner.active, false, 'Runner should be stopped');

  console.log('✅ All GuardRunner tests passed successfully!');
}

runTests().catch(err => {
  console.error('❌ GuardRunner test failed:', err);
  process.exit(1);
});
