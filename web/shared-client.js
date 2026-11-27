// ============================================================
// MaybeAI Shared Client Utilities (Auth, ReconnectingWS, XSS)
// ============================================================
(function (global) {
  "use strict";

  const TOKEN_KEY = "maybeai_creator_token";

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const CreatorAuth = {
    TOKEN_KEY,

    setToken(token) {
      const clean = String(token || "").trim();
      if (!clean) return;
      try { global.localStorage.setItem(TOKEN_KEY, clean); } catch (e) {}
      try { global.sessionStorage.setItem(TOKEN_KEY, clean); } catch (e) {}
    },

    clearToken() {
      try { global.localStorage.removeItem(TOKEN_KEY); } catch (e) {}
      try { global.sessionStorage.removeItem(TOKEN_KEY); } catch (e) {}
    },

    getToken() {
      try {
        const search = global.location && global.location.search ? global.location.search : "";
        const urlToken = new URLSearchParams(search).get("token");
        if (urlToken && urlToken.trim()) {
          const clean = urlToken.trim();
          this.setToken(clean);
          return clean;
        }
      } catch (e) {}
      try {
        return (
          global.localStorage.getItem(TOKEN_KEY) ||
          global.sessionStorage.getItem(TOKEN_KEY) ||
          global.localStorage.maybeai_creator_token ||
          ""
        );
      } catch (e) {
        return "";
      }
    },

    getAuthHeaders(extraHeaders = {}) {
      const headers = Object.assign({}, extraHeaders || {});
      const token = this.getToken();
      if (token) {
        headers["X-Creator-Token"] = token;
        headers["Authorization"] = `Bearer ${token}`;
      }
      return headers;
    },

    authFetch(url, options = {}) {
      const headers = this.getAuthHeaders(options.headers || {});
      return fetch(url, Object.assign({}, options, { headers }));
    },

    buildWsUrl(path = "/ws") {
      const loc = global.location;
      const protocol = loc && loc.protocol === "https:" ? "wss:" : "ws:";
      const host = loc ? loc.host : "localhost:7860";
      const token = this.getToken();
      let wsUrl = `${protocol}//${host}${path}`;
      if (token) {
        const sep = wsUrl.includes("?") ? "&" : "?";
        wsUrl += `${sep}token=${encodeURIComponent(token)}`;
      }
      return wsUrl;
    }
  };

  class ReconnectingWebSocket {
    constructor(urlOrFactory, options = {}) {
      this._urlOrFactory = urlOrFactory;
      this.minDelayMs = Number(options.minDelayMs) || 1000;
      this.maxDelayMs = Number(options.maxDelayMs) || 30000;
      this.factor = Number(options.factor) || 2;
      this.jitter = options.jitter !== undefined ? Number(options.jitter) : 0.25;

      this.onopen = options.onopen || null;
      this.onmessage = options.onmessage || null;
      this.onclose = options.onclose || null;
      this.onerror = options.onerror || null;
      this.onstatechange = options.onstatechange || null;

      this._ws = null;
      this._reconnectTimer = null;
      this._attempt = 0;
      this._manualClose = false;
    }

    get readyState() {
      return this._ws ? this._ws.readyState : WebSocket.CLOSED;
    }

    get isOpen() {
      return Boolean(this._ws && this._ws.readyState === WebSocket.OPEN);
    }

    _resolveUrl() {
      return typeof this._urlOrFactory === "function"
        ? this._urlOrFactory()
        : this._urlOrFactory;
    }

    _clearTimer() {
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }
    }

    _detachSocket(sock) {
      if (!sock) return;
      sock.onopen = null;
      sock.onmessage = null;
      sock.onerror = null;
      sock.onclose = null;
    }

    _computeDelayMs() {
      const base = Math.min(
        this.maxDelayMs,
        this.minDelayMs * Math.pow(this.factor, this._attempt)
      );
      const spread = base * Math.max(0, Math.min(0.5, this.jitter));
      const jitterOffset = (Math.random() * 2 - 1) * spread;
      return Math.max(this.minDelayMs, Math.round(base + jitterOffset));
    }

    connect() {
      this._manualClose = false;
      this._clearTimer();

      if (this._ws) {
        const prev = this._ws;
        this._ws = null;
        this._detachSocket(prev);
        try {
          if (prev.readyState === WebSocket.OPEN || prev.readyState === WebSocket.CONNECTING) {
            prev.close();
          }
        } catch (e) {}
      }

      if (this.onstatechange) {
        try { this.onstatechange("connecting", 0); } catch (e) {}
      }

      const url = this._resolveUrl();
      const ws = new WebSocket(url);
      this._ws = ws;

      ws.onopen = (event) => {
        if (this._ws !== ws) return;
        this._attempt = 0;
        if (this.onstatechange) {
          try { this.onstatechange("open", 0); } catch (e) {}
        }
        if (this.onopen) {
          this.onopen(event, ws);
        }
      };

      ws.onmessage = (event) => {
        if (this._ws !== ws) return;
        if (this.onmessage) {
          this.onmessage(event, ws);
        }
      };

      ws.onerror = (event) => {
        if (this._ws !== ws) return;
        if (this.onerror) {
          this.onerror(event, ws);
        }
        try { ws.close(); } catch (e) {}
      };

      ws.onclose = (event) => {
        if (this._ws !== ws) return;
        this._ws = null;
        if (this.onclose) {
          this.onclose(event);
        }
        if (!this._manualClose) {
          const delayMs = this._computeDelayMs();
          this._attempt += 1;
          if (this.onstatechange) {
            try { this.onstatechange("reconnecting", delayMs); } catch (e) {}
          }
          this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
          }, delayMs);
        } else if (this.onstatechange) {
          try { this.onstatechange("closed", 0); } catch (e) {}
        }
      };

      return ws;
    }

    reconnectNow() {
      this._attempt = 0;
      return this.connect();
    }

    send(data) {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) {
        this._ws.send(data);
        return true;
      }
      return false;
    }

    close(code, reason) {
      this._manualClose = true;
      this._clearTimer();
      if (this._ws) {
        const sock = this._ws;
        this._ws = null;
        this._detachSocket(sock);
        try {
          sock.close(code, reason);
        } catch (e) {}
      }
      if (this.onstatechange) {
        try { this.onstatechange("closed", 0); } catch (e) {}
      }
    }
  }

  global.MaybeAIClient = {
    CreatorAuth,
    ReconnectingWebSocket,
    escapeHtml
  };
})(typeof window !== "undefined" ? window : globalThis);
