/* Safety check-in timer. The server stores expires_at; JavaScript only displays the countdown. */
(function () {
  "use strict";
  var root = document.getElementById("checkin-root");
  if (!root) return;

  var urls = {
    start: root.dataset.startUrl, safe: root.dataset.safeUrl, cancel: root.dataset.cancelUrl,
    status: root.dataset.statusUrl, expire: root.dataset.expireUrl
  };
  var setupPanel = document.getElementById("setup-panel");
  var runPanel = document.getElementById("running-panel");
  var display = document.getElementById("countdown");
  var progress = document.getElementById("countdown-bar");
  var msgBox = document.getElementById("checkin-message");
  var startBtn = document.getElementById("start-timer");
  var safeBtn = document.getElementById("safe-btn");
  var cancelBtn = document.getElementById("cancel-btn");

  var deadline = null;      // local timestamp (ms) when the timer ends
  var totalSeconds = 0;
  var ticker = null, poller = null, expiring = false;

  function message(level, html) {
    msgBox.className = "alert alert-" + level;
    msgBox.innerHTML = html;
    msgBox.classList.remove("d-none");
  }

  function fmt(seconds) {
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return (h ? h + ":" : "") + pad(m) + ":" + pad(s);
  }

  function showRunning(secondsRemaining, durationMinutes) {
    // Use the SERVER's remaining seconds so a wrong laptop clock cannot shorten or extend the timer.
    deadline = Date.now() + secondsRemaining * 1000;
    totalSeconds = durationMinutes * 60;
    setupPanel.classList.add("d-none");
    runPanel.classList.remove("d-none");
    expiring = false;
    clearInterval(ticker); clearInterval(poller);
    ticker = setInterval(tick, 250);
    poller = setInterval(poll, 15000);
    tick();
  }

  function showSetup() {
    clearInterval(ticker); clearInterval(poller);
    deadline = null;
    runPanel.classList.add("d-none");
    setupPanel.classList.remove("d-none");
  }

  function tick() {
    if (deadline === null) return;
    var remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    display.textContent = fmt(remaining);
    var pct = totalSeconds ? Math.round((remaining / totalSeconds) * 100) : 0;
    progress.style.width = pct + "%";
    progress.setAttribute("aria-valuenow", pct);
    runPanel.classList.toggle("timer-warning", remaining <= 60);
    if (remaining === 0 && !expiring) expire();
  }

  function expire() {
    expiring = true;
    clearInterval(ticker);
    display.textContent = "00:00";
    message("warning", '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Time is up. Sending alert...');
    // Try for a fresh location (short wait); otherwise the server uses the last stored one.
    SWS.getLocation({ timeout: 5000, maximumAge: 60000 }).catch(function () { return null; }).then(function (pos) {
      var body = pos ? { latitude: SWS.round6(pos.latitude), longitude: SWS.round6(pos.longitude) } : {};
      return SWS.postJSON(urls.expire, body);
    }).then(function (res) {
      showSetup();
      if (res.data.expired) {
        message("danger", "<strong>Timer expired - alert created.</strong> Status: " + SWS.escapeHtml(res.data.status_label || "") +
          ". Your emergency contacts were notified. <a href='/alerts/'>View alert history</a>");
      } else {
        message("info", SWS.escapeHtml(res.data.message || res.data.error || "Timer is no longer active."));
      }
    }).catch(function () {
      message("danger", "Could not reach the server to send the alert. The server will still raise it when it next checks.");
      expiring = false;
    });
  }

  function poll() {
    SWS.getJSON(urls.status).then(function (res) {
      if (res.status === 401) return;
      if (res.data.active) {
        // Re-sync with the server clock.
        deadline = Date.now() + res.data.seconds_remaining * 1000;
      } else if (deadline !== null && !expiring) {
        window.location.reload();   // finished elsewhere (another tab, device or the server)
      }
    }).catch(function () { /* offline: keep counting locally */ });
  }

  document.querySelectorAll("[data-duration]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("[data-duration]").forEach(function (x) {
        x.classList.remove("active"); x.setAttribute("aria-pressed", "false");
      });
      b.classList.add("active"); b.setAttribute("aria-pressed", "true");
      startBtn.dataset.duration = b.dataset.duration;
      startBtn.disabled = false;
    });
  });

  startBtn.addEventListener("click", function () {
    var duration = parseInt(startBtn.dataset.duration, 10);
    if (!duration) return;
    startBtn.disabled = true;
    msgBox.classList.add("d-none");
    // Location is optional here: do not block the timer if it is unavailable.
    SWS.getLocation({ timeout: 6000, maximumAge: 60000 }).catch(function () { return null; }).then(function (pos) {
      var body = { duration: duration };
      if (pos) { body.latitude = SWS.round6(pos.latitude); body.longitude = SWS.round6(pos.longitude); }
      return SWS.postJSON(urls.start, body).then(function (res) {
        if (res.data.ok || res.status === 409) {
          showRunning(res.data.seconds_remaining, res.data.duration);
          if (!pos) message("warning", "Timer started without a location. If it expires, the alert will say the location is unavailable.");
        } else {
          message("danger", SWS.escapeHtml(res.data.error || "Could not start the timer."));
          startBtn.disabled = false;
        }
      });
    }).catch(function () {
      message("danger", "Could not reach the server. Check your connection and try again.");
      startBtn.disabled = false;
    });
  });

  function finish(url, okText) {
    safeBtn.disabled = cancelBtn.disabled = true;
    SWS.postJSON(url).then(function (res) {
      if (res.data.ok) {
        showSetup();
        message("success", okText);
        startBtn.disabled = true;
        document.querySelectorAll("[data-duration]").forEach(function (x) { x.classList.remove("active"); });
      } else {
        message("danger", SWS.escapeHtml(res.data.error || "Something went wrong."));
        if (res.status === 409 || res.status === 404) setTimeout(function () { window.location.reload(); }, 2500);
      }
    }).catch(function () {
      message("danger", "Could not reach the server. Try again - the timer is still running.");
    }).then(function () { safeBtn.disabled = cancelBtn.disabled = false; });
  }

  safeBtn.addEventListener("click", function () { finish(urls.safe, "Great - you are marked safe and the timer is stopped."); });
  cancelBtn.addEventListener("click", function () { finish(urls.cancel, "Timer cancelled. No alert was sent."); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });

  // Resume a timer that is already running (page refresh).
  if (root.dataset.activeSeconds) {
    showRunning(parseInt(root.dataset.activeSeconds, 10), parseInt(root.dataset.activeDuration, 10));
  }
})();
