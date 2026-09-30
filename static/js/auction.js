/* ==================================================================
   Auction / battle page
   ================================================================== */
(function () {
  "use strict";

  const root = document.querySelector(".auction");
  if (!root) return;

  const ROOM = root.dataset.room;
  const RP_ID = parseInt(root.dataset.rp, 10);

  const $ = (id) => document.getElementById(id);
  const pokeArt = $("pokeArt"), pokeName = $("pokeName"), pokeTypes = $("pokeTypes"),
        pokeStats = $("pokeStats"), pokeBst = $("pokeBst"), pokeAbilities = $("pokeAbilities"),
        pokeBadges = $("pokeBadges"), auctionIndex = $("auctionIndex"),
        startingBidEl = $("startingBid"), currentBidEl = $("currentBid"),
        currentBidderEl = $("currentBidder"), timerText = $("timerText"),
        ringFg = $("ringFg"), quickBids = $("quickBids"), bidForm = $("bidForm"),
        bidInput = $("bidInput"), bidHistory = $("bidHistory"),
        playerList = $("playerList"), stateBadge = $("stateBadge"),
        chatLog = $("chatLog"), chatForm = $("chatForm"), chatInput = $("chatInput"),
        chatDrawer = $("chatDrawer"), chatToggle = $("chatToggle"), chatClose = $("chatClose"),
        resultOverlay = $("resultOverlay"), resultTitle = $("resultTitle"),
        resultArt = $("resultArt"), resultText = $("resultText"),
        detailOverlay = $("detailOverlay"), detailBody = $("detailBody"),
        detailClose = $("detailClose");

  const RING_LEN = 2 * Math.PI * 52;
  ringFg.style.strokeDasharray = RING_LEN;

  let state = { room: null, players: [], you: null, auction: null };
  let countdown = null;
  let localRemaining = 0;
  let lastRenderedAuctionId = null;

  const socket = io({ transports: ["websocket", "polling"] });
  PA.bindConnectionDot(socket);

  function renderAuction(auction) {
    if (!auction) {
      pokeName.textContent = "Waiting…";
      currentBidEl.textContent = "0";
      currentBidderEl.textContent = "No active auction";
      quickBids.innerHTML = "";
      bidHistory.innerHTML = "";
      return;
    }

    const mon = auction.pokemon;
    if (lastRenderedAuctionId !== auction.id) {
      lastRenderedAuctionId = auction.id;
      pokeArt.src = PA.pokemonArt(mon);
      pokeName.textContent = mon.name;
      pokeTypes.innerHTML = (mon.types || []).map(PA.typeChip).join("");
      pokeStats.innerHTML = PA.statRows(mon);
      pokeBst.textContent = mon.bst;
      pokeAbilities.innerHTML = (mon.abilities || [])
        .map((a) => '<span class="ability">' + PA.escapeHtml(a) + "</span>").join("");
      pokeBadges.innerHTML = "";
      if (mon.is_legendary) {
        pokeBadges.innerHTML += '<span class="badge legendary">LEGENDARY</span>';
      }
      if (mon.is_mythical) {
        pokeBadges.innerHTML += '<span class="badge mythical">MYTHICAL</span>';
      }

      const idx = auction.index || 1;
      const limit = auction.limit || (state.room && state.room.auction_limit) || 0;
      auctionIndex.textContent = limit
        ? "Auction #" + idx + " / " + limit
        : "Auction #" + idx;

      startingBidEl.textContent = "Starting bid " + auction.starting_bid;
    }

    currentBidEl.textContent = auction.current_bid || 0;
    currentBidderEl.textContent = auction.current_bidder_name
      ? "Highest: " + auction.current_bidder_name
      : "No bids yet";

    renderQuickBids(auction);
    renderBidHistory(auction.bid_history || []);
    setRemaining(auction.remaining);
  }

  function renderQuickBids(auction) {
    const you = state.you || {};
    const full = you.team_size >= (state.room ? state.room.team_size : 4);
    const disabled = full || !you.coins;

    const buttons = [];
    [10, 25, 50].forEach((step) => {
      const value = auction.current_bid ? auction.current_bid + step : auction.starting_bid;
      buttons.push({ label: "+" + step, value: Math.min(value, you.coins || 0) });
    });
    buttons.push({ label: "MAX", value: you.coins || 0 });

    quickBids.innerHTML = buttons.map((b) =>
      '<button class="btn btn-ghost btn-sm" data-bid="' + b.value + '"' +
      (disabled ? " disabled" : "") + ">" + b.label + "</button>"
    ).join("");

    quickBids.querySelectorAll("[data-bid]").forEach((btn) => {
      btn.addEventListener("click", () => submitBid(btn.dataset.bid));
    });
  }

  function renderBidHistory(history) {
    bidHistory.innerHTML = history.slice().reverse().map((b, i) =>
      '<li class="' + (i === 0 ? "new" : "") + '"><span>' + PA.escapeHtml(b.name) +
      "</span><b>" + b.amount + "</b></li>"
    ).join("");
  }

  function renderPlayers() {
    playerList.innerHTML = "";
    const teamMax = (state.room && state.room.team_size) || 4;

    (state.players || []).forEach((p) => {
      const card = document.createElement("div");
      card.className = "player-card" +
        (p.id === RP_ID ? " me" : "") +
        (p.completed ? " done" : "");

      const coins = p.coins === null || p.coins === undefined
        ? "•••" : p.coins;

      card.innerHTML =
        '<div class="pc-head">' +
          '<span class="pc-name">' + PA.escapeHtml(p.name) +
            (p.is_host ? " 👑" : "") + "</span>" +
          '<span class="pc-coins">' + coins + " 🪙</span>" +
        "</div>" +
        '<div class="pc-progress">' + p.team_size + "/" + teamMax +
          " Pokémon" + (p.completed ? " · COMPLETE" : "") +
          (p.connected ? "" : " · offline") + "</div>" +
        '<div class="mini-team"></div>';

      const grid = card.querySelector(".mini-team");
      for (let i = 0; i < teamMax; i++) {
        const slot = document.createElement("div");
        const mon = (p.team || [])[i];
        if (mon) {
          slot.className = "mini-slot filled";
          slot.innerHTML = '<img src="' + PA.pokemonArt(mon) +
                           '" alt="' + PA.escapeHtml(mon.name) + '">';
          slot.title = mon.name;
          slot.addEventListener("click", () => showDetails(mon));
        } else {
          slot.className = "mini-slot empty";
        }
        grid.appendChild(slot);
      }

      playerList.appendChild(card);
    });
  }

  function showDetails(mon) {
    detailBody.innerHTML =
      '<h2 style="margin:0 0 10px">' + PA.escapeHtml(mon.name) + "</h2>" +
      '<img src="' + PA.pokemonArt(mon) + '" alt="" style="max-width:150px">' +
      '<div class="type-row">' + (mon.types || []).map(PA.typeChip).join("") + "</div>" +
      '<div class="stat-grid">' + PA.statRows(mon) + "</div>" +
      '<div class="bst-bar"><span>Base Stat Total</span><b>' + mon.bst + "</b></div>" +
      '<div class="ability-row">' +
        (mon.abilities || []).map((a) => '<span class="ability">' + PA.escapeHtml(a) + "</span>").join("") +
      "</div>";
    detailOverlay.hidden = false;
  }

  function setRemaining(seconds) {
    localRemaining = Math.max(0, Math.ceil(seconds || 0));
    paintTimer();
    if (countdown) clearInterval(countdown);
    countdown = setInterval(() => {
      localRemaining = Math.max(0, localRemaining - 1);
      paintTimer();
      if (localRemaining <= 0 && countdown) {
        clearInterval(countdown);
        countdown = null;
      }
    }, 1000);
  }

  function paintTimer() {
    const total = (state.auction && state.auction.duration) || 20;
    timerText.textContent = localRemaining;
    const pct = Math.min(1, localRemaining / total);
    ringFg.style.strokeDashoffset = RING_LEN * (1 - pct);

    ringFg.classList.toggle("warn", localRemaining <= 10 && localRemaining > 5);
    ringFg.classList.toggle("danger", localRemaining <= 5);
  }

  function submitBid(raw) {
    const value = parseInt(raw, 10);
    if (!Number.isFinite(value) || value <= 0) {
      PA.toast("Enter a valid whole number.", "error");
      return;
    }
    socket.emit("place_bid", { amount: value });
  }

  bidForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitBid(bidInput.value);
    bidInput.value = "";
  });

  function pushChat(msg) {
    const div = document.createElement("div");
    div.className = "chat-msg" + (msg.system ? " system" : "");
    if (msg.system) {
      div.textContent = msg.text;
    } else {
      div.innerHTML = '<span class="who">' + PA.escapeHtml(msg.name) + ":</span> " +
        PA.escapeHtml(msg.text) +
        '<span class="time">' + PA.timeAgo(msg.ts) + "</span>";
    }
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    socket.emit("chat_message", { text: text });
    chatInput.value = "";
  });

  chatToggle.addEventListener("click", () => chatDrawer.classList.toggle("open"));
  chatClose.addEventListener("click", () => chatDrawer.classList.remove("open"));

  detailClose.addEventListener("click", () => (detailOverlay.hidden = true));
  detailOverlay.addEventListener("click", (e) => {
    if (e.target === detailOverlay) detailOverlay.hidden = true;
  });

  socket.on("connect", () => socket.emit("join_room", { room_code: ROOM }));

  socket.on("state_sync", (data) => {
    state = data;
    if (data.room) {
      stateBadge.textContent = data.room.state;
    }
    renderAuction(data.auction);
    renderPlayers();

    if (data.room && data.room.state === "FINISHED") {
      window.location.href = "/room/" + ROOM + "/results";
    }
  });

  socket.on("auction_started", (d) => {
    state.auction = d.auction;
    lastRenderedAuctionId = null;
    renderAuction(d.auction);
    PA.toast(
      "Auction #" + (d.auction.index || 1) +
      (d.auction.limit ? "/" + d.auction.limit : "") +
      ": " + d.auction.pokemon.name,
      "success"
    );
  });

  socket.on("auction_tick", (d) => {
    if (!state.auction || d.id !== state.auction.id) return;
    localRemaining = d.remaining;
    paintTimer();
  });

  socket.on("bid_placed", (d) => {
    if (state.auction) {
      state.auction.current_bid = d.current_bid;
      state.auction.current_bidder = d.current_bidder;
      state.auction.current_bidder_name = d.bidder_name;
      state.auction.remaining = d.remaining;
      if (!state.auction.bid_history) state.auction.bid_history = [];
      state.auction.bid_history.push({ name: d.bidder_name, amount: d.amount });

      currentBidEl.textContent = d.current_bid;
      currentBidEl.classList.add("bump");
      setTimeout(() => currentBidEl.classList.remove("bump"), 200);
      currentBidderEl.textContent = "Highest: " + d.bidder_name;
      renderBidHistory(state.auction.bid_history);
      renderQuickBids(state.auction);
      if (d.bidder === RP_ID) {
        localRemaining = Math.ceil(d.remaining);
        paintTimer();
      }
    }
  });

  socket.on("auction_extended", (d) => {
    PA.toast("⏱ Anti-snipe! Timer reset to " + d.remaining + "s", "error");
    localRemaining = d.remaining;
    paintTimer();
  });

  socket.on("bid_accepted", (d) => {
    if (state.you) state.you.coins = d.coins;
    PA.toast("Bid placed: " + d.amount + " 🪙", "success");
  });

  socket.on("bid_rejected", (d) => PA.toast(d.error, "error"));
  socket.on("error_message", (d) => { if (d && d.error) PA.toast(d.error, "error"); });

  socket.on("auction_ended", (d) => {
    if (d.sold) {
      resultTitle.textContent = "Sold!";
      resultArt.src = PA.pokemonArt(d.pokemon);
      resultText.textContent = d.winner_name + " wins " + d.pokemon.name +
        " for " + d.price + " coins.";
    } else {
      resultTitle.textContent = "No bids";
      resultArt.src = PA.pokemonArt(d.pokemon);
      resultText.textContent = d.pokemon.name + " went unsold.";
    }
    resultOverlay.hidden = false;
    setTimeout(() => (resultOverlay.hidden = true), 3200);
    if (countdown) { clearInterval(countdown); countdown = null; }
  });

  socket.on("player_team_updated", () => socket.emit("request_state"));
  socket.on("player_joined", () => socket.emit("request_state"));
  socket.on("player_left", () => socket.emit("request_state"));
  socket.on("host_changed", () => socket.emit("request_state"));

  socket.on("chat_message", pushChat);

  socket.on("auction_complete", () => {
    PA.toast("Auction complete! Running battles…", "success");
    stateBadge.textContent = "BATTLE";
  });

  socket.on("game_finished", () => {
    PA.toast("Battles finished! Loading results…", "success");
    setTimeout(() => (window.location.href = "/room/" + ROOM + "/results"), 900);
  });

  socket.on("room_closed", () => {
    PA.toast("The host closed the room.", "error");
    setTimeout(() => (window.location.href = "/"), 1200);
  });

  socket.on("sync_error", () => {
    window.location.href = "/join?code=" + encodeURIComponent(ROOM);
  });
})();
