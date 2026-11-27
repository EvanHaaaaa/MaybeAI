# Third-Party Notices and Attributions

MaybeAI is licensed under the MIT License (see [LICENSE](LICENSE)). This repository includes or integrates the following third-party open-source components and project assets:

## 1. Vendored Frontend Libraries (`web/vendor/`)

- **Three.js (`r169`)** — `web/vendor/three.module.js`, `web/vendor/GLTFLoader.js`, `web/vendor/BufferGeometryUtils.js`
  - Copyright © 2010–2024 Three.js Authors
  - License: **MIT** (<https://github.com/mrdoob/three.js/blob/dev/LICENSE>)
- **@pixiv/three-vrm (`v3.2.0`)** — `web/vendor/three-vrm.module.js`
  - Copyright © 2019–2024 pixiv Inc.
  - License: **MIT** (<https://github.com/pixiv/three-vrm/blob/dev/LICENSE>)

## 2. Node.js / Minecraft Bridge (`minecraft/package.json`)

- **mineflayer**, **mineflayer-pathfinder**, **mineflayer-pvp**, **prismarine-viewer**, **vec3**, **ws** — Installed via `npm install` in `minecraft/` (not vendored in Git).
  - License: **MIT** / respective upstream licenses.

## 3. Python Dependencies (`requirements.txt` & `pyproject.toml`)

- Core & optional Python packages (`fastapi`, `uvicorn`, `websockets`, `aiohttp`, `edge-tts`, `pydantic`, `python-dotenv`, `requests`, `pygame`, `numpy`, `python-chess`, `pillow`, `mss`, `tiktoken`, `yt-dlp`, etc.) are installed via `pip` / `uv` under their respective open-source licenses (MIT / BSD / Apache-2.0 / LGPL-2.1 / Unlicense).

## 4. Bundled Demo Audio Asset (`assets/songs/`)

- `assets/songs/digital_world_bgm.wav` — Original demo instrumental track bundled with MaybeAI for local karaoke testing (`config/songs.json`). Provided under the repository MIT License; creators may replace or remove it for live broadcasts.
