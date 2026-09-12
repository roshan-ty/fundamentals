/* Bulls & Bears Fundamentals — boot */
"use strict";
(function () {
  const B = window.BBF;
  const TABS = [
    { id: "home", label: "Home" },
    { id: "data", label: "Data" },
    { id: "calendar", label: "Calendar" },
    { id: "news", label: "News Feed" },
    { id: "bias", label: "Bias" },
    { id: "cftc", label: "CFTC" },
    { id: "historical", label: "Historical Data" },
    { id: "analysis", label: "Analysis" },
    { id: "setups", label: "Top Setups" },
  ];
  function init() {
    const hash = (window.location.hash || "#home").slice(1);
    const valid = TABS.map((t) => t.id).includes(hash);
    B.setupThemeToggle();
    B.tickClock();
    setInterval(B.tickClock, 1000);
    B.switchTab(valid ? hash : "home");
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();