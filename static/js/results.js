/* ==================================================================
   Results page — reveal animation for the leaderboard
   ================================================================== */
(function () {
  "use strict";

  const rows = document.querySelectorAll("#leaderboardList .lb-row");
  rows.forEach((row, i) => {
    row.style.opacity = "0";
    row.style.transform = "translateY(12px)";
    row.style.transition = "opacity .35s ease, transform .35s ease";
    setTimeout(() => {
      row.style.opacity = "1";
      row.style.transform = "none";
    }, 90 * i + 120);
  });

  const first = document.querySelector("#leaderboardList .rank-1");
  if (first) {
    setTimeout(() => PA.toast("🏆 " + first.querySelector(".lb-name").textContent +
                              " wins!", "success", 6000), 600);
  }
})();