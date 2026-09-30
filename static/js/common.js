/* ==================================================================
   Shared helpers — toasts, escaping, socket connection indicator
   ================================================================== */
(function (global) {
  "use strict";

  const PA = global.PA || (global.PA = {});

  /* -------------------- toasts -------------------- */
  PA.toast = function (message, type, timeout) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "toast" + (type ? " " + type : "");
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => {
      el.style.transition = "opacity .3s, transform .3s";
      el.style.opacity = "0";
      el.style.transform = "translateX(30px)";
      setTimeout(() => el.remove(), 320);
    }, timeout || 3200);
  };

  /* -------------------- escaping -------------------- */
  PA.escapeHtml = function (value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  };

  /* -------------------- time -------------------- */
  PA.timeAgo = function (ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  /* -------------------- pokemon helpers -------------------- */
  PA.typeChip = function (type) {
    return '<span class="type-chip type-' + PA.escapeHtml(type) + '">' +
           PA.escapeHtml(type) + "</span>";
  };

  PA.pokemonArt = function (mon) {
    return (mon && (mon.artwork || mon.sprite)) || "";
  };

  PA.statRows = function (mon) {
    const rows = [
      ["HP", mon.hp], ["Attack", mon.attack], ["Defense", mon.defense],
      ["Sp. Atk", mon.sp_attack], ["Sp. Def", mon.sp_defense], ["Speed", mon.speed],
    ];
    return rows.map(([label, value]) =>
      '<div class="stat-row"><span>' + label + "</span><b>" + value + "</b></div>"
    ).join("");
  };

  /* -------------------- connection indicator -------------------- */
  PA.bindConnectionDot = function (socket) {
    const dot = document.getElementById("connDot");
    if (!dot) return;
    const update = () => {
      dot.classList.toggle("online", socket.connected);
      dot.classList.toggle("offline", !socket.connected);
      dot.title = socket.connected ? "Connected" : "Disconnected";
    };
    socket.on("connect", update);
    socket.on("disconnect", update);
    update();
  };

  /* -------------------- misc -------------------- */
  PA.debounce = function (fn, wait) {
    let t;
    return function () {
      const args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(self, args), wait);
    };
  };

  PA.qs = function (name) {
    return new URLSearchParams(location.search).get(name);
  };
})(window);