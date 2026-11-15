/**
 * Mineflayer Bot Bridge for MaybeAI (Eve Maybe)
 * Connects to Minecraft Java Server, handles autonomous movement,
 * pathfinding, player following, and bridges events to Python via WebSocket.
 */
process.on('uncaughtException', (err) => {
  // Catch non-fatal packet parsing quirks on modern Paper servers
  console.log('[Mineflayer SafeGuard] Handled packet warning:', err.message);
});

const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const WebSocket = require('ws');
const fs = require('fs');

const config = JSON.parse(fs.readFileSync('./config.json', 'utf8'));

let bot = null;
let activeWs = null;
let currentMode = config.default_mode || 'santai';
let followingTarget = null;
let isWandering = true;
let autonomyInterval = null;

// Initialize WebSocket Bridge Server for Python on 25566
const wsServer = new WebSocket.Server({ port: config.bridge_ws_port });
console.log(`[Minecraft Bridge] WebSocket bridge listening on ws://localhost:${config.bridge_ws_port}`);

wsServer.on('connection', (ws) => {
  console.log('[Minecraft Bridge] Python Controller connected to bridge!');
  activeWs = ws;

  if (bot && bot.entity) {
    sendToPython('bot_spawned', {
      username: bot.username,
      pos: bot.entity.position,
      health: bot.health !== undefined ? bot.health : 20,
      food: bot.food !== undefined ? bot.food : 20
    });
  }

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);
      handlePythonCommand(data);
    } catch (e) {
      console.error('[Bridge Error] Malformed JSON:', e);
    }
  });

  ws.on('close', () => {
    console.log('[Minecraft Bridge] Python Controller disconnected.');
    activeWs = null;
  });
});

function sendToPython(eventType, data) {
  if (activeWs && activeWs.readyState === WebSocket.OPEN) {
    activeWs.send(JSON.stringify({ type: eventType, data: data }));
  }
}

function getNearestPlayer() {
  if (!bot || !bot.entity) return null;
  let nearest = null;
  let minDist = 16;

  for (const name in bot.players) {
    if (name === bot.username) continue;
    const player = bot.players[name];
    if (player && player.entity) {
      const dist = bot.entity.position.distanceTo(player.entity.position);
      if (dist < minDist) {
        minDist = dist;
        nearest = player;
      }
    }
  }
  return nearest;
}

function startAutonomyLoop() {
  if (autonomyInterval) clearInterval(autonomyInterval);

  let wanderCooldown = 0;

  autonomyInterval = setInterval(() => {
    if (!bot || !bot.entity || !bot.pathfinder) return;

    try {
      // 1. Follow Player Logic
      if (followingTarget) {
        const player = bot.players[followingTarget];
        if (player && player.entity) {
          const dist = bot.entity.position.distanceTo(player.entity.position);
          if (dist > 2.5) {
            bot.pathfinder.setGoal(new goals.GoalFollow(player.entity, 2), true);
          }
          // Face the player
          bot.lookAt(player.entity.position.offset(0, 1.6, 0));
          return;
        } else {
          followingTarget = null;
        }
      }

      // 2. Look-at Nearby Players (Social Head Tracking)
      const nearest = getNearestPlayer();
      if (nearest && nearest.entity) {
        const dist = bot.entity.position.distanceTo(nearest.entity.position);
        if (dist <= 8) {
          bot.lookAt(nearest.entity.position.offset(0, 1.6, 0));
        }
      } else {
        // Natural idle head wandering
        if (Math.random() < 0.25) {
          const randomYaw = bot.entity.yaw + (Math.random() - 0.5) * 1.2;
          const randomPitch = (Math.random() - 0.5) * 0.4;
          bot.look(randomYaw, randomPitch, false);
        }
      }

      // 3. Autonomous Wandering in Mode Santai
      if (currentMode === 'santai' && isWandering) {
        wanderCooldown++;
        if (wanderCooldown >= 8) { // Every ~12 seconds
          wanderCooldown = 0;
          if (!bot.pathfinder.isMoving()) {
            const rx = (Math.random() - 0.5) * 12;
            const rz = (Math.random() - 0.5) * 12;
            const targetPos = bot.entity.position.offset(rx, 0, rz);
            bot.pathfinder.setGoal(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 1));
          }
        }
      }

    } catch (e) {
      console.log('[Autonomy Error]', e.message);
    }
  }, 1500);
}

function createBot(host, port, username, version) {
  const targetHost = host || config.server_host;
  const targetPort = port || config.server_port;
  const targetUser = username || config.bot_username || 'EveMaybe';
  const targetVer = version || config.minecraft_version || '1.21.1';

  console.log(`[Mineflayer] Connecting to ${targetHost}:${targetPort} as ${targetUser} (v${targetVer})...`);

  if (bot) {
    try { bot.quit(); } catch (e) {}
    bot = null;
  }

  bot = mineflayer.createBot({
    host: targetHost,
    port: parseInt(targetPort),
    username: targetUser,
    version: targetVer
  });

  bot.loadPlugin(pathfinder);

  bot.on('login', () => {
    console.log(`[Mineflayer] Logged in to ${targetHost}! Waiting for spawn chunk...`);
  });

  bot.on('spawn', () => {
    console.log(`[Mineflayer] Eve spawned successfully in world at:`, bot.entity.position);

    // Initialize Movements & Pathfinder with server version
    try {
      const mcData = require('minecraft-data')(bot.version);
      const moves = new Movements(bot, mcData);
      moves.allowParkour = true;
      moves.canDig = false; // Don't break random blocks in casual
      bot.pathfinder.setMovements(moves);
      console.log('[Mineflayer] Movements and pathfinding initialized!');
    } catch (e) {
      console.log('[Mineflayer] Pathfinder setup notice:', e.message);
    }

    sendToPython('bot_spawned', {
      username: bot.username,
      pos: bot.entity.position,
      health: bot.health !== undefined ? bot.health : 20,
      food: bot.food !== undefined ? bot.food : 20
    });

    // Start lively autonomous movements & look-around
    startAutonomyLoop();
  });

  // Handle in-game chat commands directly from other players
  bot.on('chat', (sender, message) => {
    if (sender === bot.username) return;
    console.log(`[In-Game Chat] <${sender}>: ${message}`);

    const lower = message.toLowerCase();

    // Player invites Eve to follow
    if (lower.includes('sini') || lower.includes('follow') || lower.includes('ikut')) {
      followingTarget = sender;
      bot.chat(`Otw ke kamu, ${sender}! ✨`);
      const player = bot.players[sender];
      if (player && player.entity && bot.pathfinder) {
        bot.pathfinder.setGoal(new goals.GoalFollow(player.entity, 2), true);
      }
    } else if (lower.includes('stop') || lower.includes('diam') || lower.includes('stay')) {
      followingTarget = null;
      if (bot.pathfinder) bot.pathfinder.setGoal(null);
      bot.chat(`Oke, aku stand by di sini ya ${sender}!`);
    } else if (lower.includes('jump') || lower.includes('lompat')) {
      bot.setControlState('jump', true);
      setTimeout(() => bot.setControlState('jump', false), 400);
      bot.chat('Hup! Lompat! 😄');
    }

    sendToPython('player_chat', { username: sender, message: message });
  });

  // Handle taking damage
  bot.on('entityHurt', (entity) => {
    if (entity === bot.entity) {
      console.log(`[Mineflayer] Eve took damage! Health: ${bot.health}`);
      // Jump and look back when hurt
      bot.setControlState('jump', true);
      setTimeout(() => bot.setControlState('jump', false), 350);
      sendToPython('bot_hurt', {
        health: bot.health,
        source: 'damage'
      });
    }
  });

  // Periodic proximity check for nearby players
  setInterval(() => {
    if (!bot || !bot.entity) return;

    for (const entityName in bot.entities) {
      const entity = bot.entities[entityName];
      if (entity.type === 'player' && entity.username && entity.username !== bot.username) {
        const dist = bot.entity.position.distanceTo(entity.position);
        if (dist <= 10) {
          sendToPython('player_nearby', {
            username: entity.username,
            distance: Math.round(dist * 10) / 10
          });
        }
      }
    }
  }, 3000);

  bot.on('kicked', (reason) => {
    console.log('[Mineflayer] Kicked from server:', reason);
    if (autonomyInterval) clearInterval(autonomyInterval);
    const reasonStr = typeof reason === 'object' ? JSON.stringify(reason) : String(reason);
    sendToPython('bot_kicked', { reason: reasonStr });
  });

  bot.on('error', (err) => {
    console.log('[Mineflayer] Connection Error:', err.message);
    sendToPython('bot_error', { message: err.message });
  });

  bot.on('end', (reason) => {
    console.log('[Mineflayer] Bot session ended:', reason);
    if (autonomyInterval) clearInterval(autonomyInterval);
    sendToPython('bot_disconnected', { reason: String(reason) });
  });
}

function handlePythonCommand(cmd) {
  if (cmd.action === 'connect_server') {
    createBot(cmd.host, cmd.port, cmd.username, cmd.version);
    return;
  }

  if (cmd.action === 'disconnect_server') {
    console.log('[Mineflayer] Disconnecting bot from server...');
    if (autonomyInterval) clearInterval(autonomyInterval);
    if (bot) {
      try { bot.quit(); } catch (e) {}
      bot = null;
    }
    sendToPython('bot_disconnected', { reason: 'User requested' });
    return;
  }

  if (!bot) return;

  if (cmd.action === 'chat') {
    bot.chat(cmd.message);
  } else if (cmd.action === 'set_mode') {
    currentMode = cmd.mode;
    console.log(`[Mineflayer] Mode set to: ${currentMode}`);
  } else if (cmd.action === 'crouch') {
    bot.setControlState('sneak', true);
    setTimeout(() => bot.setControlState('sneak', false), 800);
  } else if (cmd.action === 'jump') {
    bot.setControlState('jump', true);
    setTimeout(() => bot.setControlState('jump', false), 400);
  } else if (cmd.action === 'follow_nearest') {
    const nearest = getNearestPlayer();
    if (nearest && nearest.entity && bot.pathfinder) {
      followingTarget = nearest.username;
      bot.chat(`Mengikuti ${nearest.username}!`);
      bot.pathfinder.setGoal(new goals.GoalFollow(nearest.entity, 2), true);
    }
  } else if (cmd.action === 'stop_moving') {
    followingTarget = null;
    if (bot.pathfinder) bot.pathfinder.setGoal(null);
  } else if (cmd.action === 'toggle_wander') {
    isWandering = !isWandering;
    console.log(`[Mineflayer] Wandering: ${isWandering}`);
  }
}
