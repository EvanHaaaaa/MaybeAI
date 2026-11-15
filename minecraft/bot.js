/**
 * Mineflayer Bot Bridge for MaybeAI (Eve)
 * Connects to Minecraft Java Server & bridges events to Python via WebSocket.
 */
const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const WebSocket = require('ws');
const fs = require('fs');

const config = JSON.parse(fs.readFileSync('./config.json', 'utf8'));

let bot = null;
let wsServer = null;
let activeWs = null;
let currentMode = config.default_mode || 'santai';

// Initialize WebSocket Bridge Server for Python
wsServer = new WebSocket.Server({ port: config.bridge_ws_port });
console.log(`[Minecraft Bridge] WebSocket bridge listening on ws://localhost:${config.bridge_ws_port}`);

wsServer.on('connection', (ws) => {
  console.log('[Minecraft Bridge] Python Controller connected to bridge!');
  activeWs = ws;

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

function createBot() {
  console.log(`[Mineflayer] Connecting to ${config.server_host}:${config.server_port} as ${config.bot_username}...`);

  bot = mineflayer.createBot({
    host: config.server_host,
    port: config.server_port,
    username: config.bot_username,
    version: config.minecraft_version
  });

  bot.loadPlugin(pathfinder);

  bot.on('spawn', () => {
    console.log('[Mineflayer] Eve has spawned in Minecraft!');
    sendToPython('bot_spawned', {
      username: bot.username,
      pos: bot.entity.position,
      health: bot.health,
      food: bot.food
    });
  });

  // Handle in-game chat
  bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    console.log(`[In-Game Chat] <${username}>: ${message}`);
    sendToPython('player_chat', { username, message });
  });

  // Handle taking damage
  bot.on('entityHurt', (entity) => {
    if (entity === bot.entity) {
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
    sendToPython('bot_kicked', { reason });
  });

  bot.on('error', (err) => {
    console.log('[Mineflayer] Bot Error:', err.message);
  });

  bot.on('end', () => {
    console.log('[Mineflayer] Bot disconnected. Retrying in 10s...');
    setTimeout(createBot, 10000);
  });
}

function handlePythonCommand(cmd) {
  if (!bot) return;

  if (cmd.action === 'chat') {
    bot.chat(cmd.message);
  } else if (cmd.action === 'set_mode') {
    currentMode = cmd.mode;
    console.log(`[Minecraft Bridge] Mode switched to: ${currentMode}`);
  } else if (cmd.action === 'crouch') {
    bot.setControlState('sneak', true);
    setTimeout(() => bot.setControlState('sneak', false), 800);
  } else if (cmd.action === 'follow' && cmd.username) {
    const target = bot.players[cmd.username]?.entity;
    if (target) {
      const defaultMove = new Movements(bot);
      bot.pathfinder.setMovements(defaultMove);
      bot.pathfinder.setGoal(new goals.GoalFollow(target, 2), true);
    }
  }
}

// Start bot if server is accessible
createBot();
