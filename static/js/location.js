/* Live Location page. */
(function () {
  "use strict";
  var btn = document.getElementById("get-location");
  if (!btn) return;
  var latEl = document.getElementById("loc-lat");
  var lonEl = document.getElementById("loc-lon");
  var accEl = document.getElementById("loc-acc");
  var timeEl = document.getElementById("loc-time");
  var linkEl = document.getElementById("loc-link");
  var copyBtn = document.getElementById("copy-link");
  var errorBox = document.getElementById("loc-error");
  var currentLink = "";

  function setError(message) {
    errorBox.textContent = message || "";
    errorBox.classList.toggle("d-none", !message);
  }

  function refresh() {
    setError("");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Locating...';
    SWS.getLocation({ timeout: 15000 }).then(function (pos) {
      var lat = SWS.round6(pos.latitude), lon = SWS.round6(pos.longitude);
      latEl.textContent = lat;
      lonEl.textContent = lon;
      accEl.textContent = pos.accuracy ? Math.round(pos.accuracy) + " m" : "unknown";
      timeEl.textContent = new Date().toLocaleTimeString();
      currentLink = SWS.mapLink(lat, lon);
      linkEl.href = currentLink;
      linkEl.classList.remove("disabled");
      linkEl.removeAttribute("aria-disabled");
      copyBtn.disabled = false;
      SWS.showMap("live-map", lat, lon, pos.accuracy);
    }).catch(function (err) {
      setError(err && err.message ? err.message : "Could not get your location.");
    }).then(function () {
      btn.disabled = false;
      btn.innerHTML = "Refresh location";
    });
  }

  btn.addEventListener("click", refresh);

  copyBtn.addEventListener("click", function () {
    if (!currentLink) return;
    var done = function () { copyBtn.textContent = "Copied!"; setTimeout(function () { copyBtn.textContent = "Copy link"; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(currentLink).then(done, function () { window.prompt("Copy this link:", currentLink); });
    } else {
      window.prompt("Copy this link:", currentLink);
    }
  });

  window.addEventListener("offline", function () { setError("You are offline. Location may not update until you reconnect."); });
  window.addEventListener("online", function () { setError(""); });

  refresh();
})();
