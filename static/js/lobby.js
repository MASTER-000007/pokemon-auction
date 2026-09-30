/* ==================================================================
   Lobby page
   ================================================================== */
(function () {
  "use strict";

  const root = document.querySelector(".lobby");
  if (!root) return;

  const ROOM = root.dataset.room;
  const RP_ID = parseInt(root.dataset.rp, 10);

  const playerList = document.getElementById("playerList");
  const playerCount = document.getElementById("playerCount");
  const startBtn = document.getElementById("startBtn");
  const startHint = document.getElementById("startHint");
  const endBtn = document.getElementById("endBtn");
  const settingsDisplay = document.getElementById("settingsDisplay");
  const chatLog = document.getElementById("chatLog");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const copyBtn = document.getElementById("copyCode");

  let state = { room: null, players: [], you: null };

  const socket = io({ transports: ["websocket", "polling"] });
  PA.bindConnectionDot(socket);

  /* -------------------- rendering -------------------- */
  function renderPlayers() {
    playerList.innerHTML = "";
    const players = state.players || [];
    playerCount.textContent = players.length;

    players.forEach((p) => {
      const li = document.createElement("li");

      const avatar = document.createElement("span");
      avatar.className = "p-avatar";
      avatar.textContent = (p.name || "?").charAt(0).toUpperCase();

      const name = document.createElement("span");
      name.className = "p-name";
      name.textContent = p.name;

      li.appendChild(avatar);
      li.appendChild(name);

      if (p.is_host) {
        const badge = document.createElement("span");
        badge.className = "p-badge";
        badge.textContent = "HOST";
        li.appendChild(badge);
      }

      if (!p.connected) {
        const badge = document.createElement("span");
        badge.className = "p-badge off";
        badge.textContent = "OFFLINE";
        li.appendChild(badge);
      }

      if (state.you && state.you.is_host && p.id !== RP_ID) {
        const kick = document.createElement("button");
        kick.className = "btn btn-danger btn-xs";
        kick.textContent = "Kick";
        kick.addEventListener("click", () => {
          socket.emit("kick_player", { player_id: p.id });
        });
        li.appendChild(kick);
      }

      playerList.appendChild(li);
    });

    const isHost = !!(state.you && state.you.is_host);

    // Robust fallbacks: server may or may not include these in every snapshot.
    const minPlayers = (state.room && Number(state.room.min_players)) || 2;
    const maxPlayers = (state.room && Number(state.room.max_players)) || 8;

    const enough = players.length >= minPlayers;
    const allConnected = players.every((p) => p.connected);

    startBtn.hidden = !isHost;
    endBtn.hidden = !isHost;
    startBtn.disabled = !isHost || !enough;

    if (!isHost) {
      startHint.textContent = "Waiting for the host to start the game…";
    } else if (!enough) {
      startHint.textContent =
        "Need at least " + minPlayers + " players (" +
        players.length + "/" + maxPlayers + " joined).";
    } else if (!allConnected) {
      startHint.textContent = "All players must be online to start.";
    } else {
      startHint.textContent = "Everyone is ready!";
    }
  }

  function renderSettings() {
    const s = (state.room && state.room.settings) || {};
    const rows = [
      ["Starting coins", s.starting_coins],
      ["Pokémon per player", s.team_size],
      ["Max players", s.max_players],
      ["Auction timer", s.auction_duration + "s"],
      ["Min bid increment", s.min_bid_increment],
      ["Anti-snipe", s.anti_snipe_enabled ? s.anti_snipe_seconds + "s" : "Off"],
      ["Duplicates", s.allow_duplicates ? "Allowed" : "Blocked"],
      ["Legendaries", s.allow_legendaries ? "Included" : "Excluded"],
      ["Mythicals", s.allow_mythicals ? "Included" : "Excluded"],
      ["Balances visible", s.show_balances ? "Yes" : "No"],
    ];
    settingsDisplay.innerHTML = rows.map(([k, v]) =>
      "<div><span>" + PA.escapeHtml(k) + "</span><b>" + PA.escapeHtml(v) + "</b></div>"
    ).join("");
  }

  function pushChat(msg) {
    const div = document.createElement("div");
    div.className = "chat-msg" + (msg.system ? " system" : "");
    if (msg.system) {
      div.textContent = msg.text;
    } else {
      div.innerHTML =
        '<span class="who">' + PA.escapeHtml(msg.name) + ":</span> " +
        PA.escapeHtml(msg.text) +
        '<span class="time">' + PA.timeAgo(msg.ts) + "</span>";
    }
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  /* -------------------- socket events -------------------- */
  socket.on("connect", () => {
    socket.emit("join_room", { room_code: ROOM });
  });

  socket.on("state_sync", (data) => {
    state = data;
    renderPlayers();
    renderSettings();

    if (data.room && data.room.state !== "LOBBY") {
      window.location.href = "/room/" + ROOM + "/game";
    }
  });

  socket.on("player_joined", () => socket.emit("request_state"));
  socket.on("player_left", () => socket.emit("request_state"));
  socket.on("player_kicked", (d) => {
    if (d.id === RP_ID) {
      PA.toast("You were removed from the room.", "error");
      setTimeout(() => (window.location.href = "/"), 1200);
    } else {
      socket.emit("request_state");
    }
  });
  socket.on("host_changed", (d) => {
    PA.toast(d.name + " is now the host.");
    socket.emit("request_state");
  });
  socket.on("settings_updated", () => socket.emit("request_state"));

  socket.on("chat_message", pushChat);

  socket.on("game_started", () => {
    PA.toast("Game starting…", "success");
    setTimeout(() => (window.location.href = "/room/" + ROOM + "/game"), 700);
  });

  socket.on("room_closed", () => {
    PA.toast("The host closed the room.", "error");
    setTimeout(() => (window.location.href = "/"), 1200);
  });

  socket.on("error_message", (d) => {
    if (d && d.error) PA.toast(d.error, "error");
  });
  socket.on("sync_error", () => {
    window.location.href = "/join?code=" + encodeURIComponent(ROOM);
  });

  /* -------------------- UI actions -------------------- */
  startBtn.addEventListener("click", () => socket.emit("start_game"));
  endBtn.addEventListener("click", () => {
    if (confirm("Close this room for everyone?")) socket.emit("end_room");
  });

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    socket.emit("chat_message", { text: text });
    chatInput.value = "";
  });

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const link = window.location.origin + "/join?code=" + encodeURIComponent(ROOM);
      try {
        await navigator.clipboard.writeText(link);
        PA.toast("Invite link copied!", "success");
      } catch (err) {
        window.prompt("Copy this invite link:", link);
      }
    });
  }
})();