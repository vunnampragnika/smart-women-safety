/* SOS flow: confirm -> get location -> map -> create alert -> show result. */
(function () {
  "use strict";
  var button = document.getElementById("sos-button");
  if (!button) return;

  var modalEl = document.getElementById("sosConfirmModal");
  var confirmBtn = document.getElementById("sos-confirm");
  var statusBox = document.getElementById("sos-status");
  var url = button.dataset.url;
  var modal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  var busy = false;

  function show(level, html) {
    statusBox.className = "alert alert-" + level + " mt-3";
    statusBox.innerHTML = html;
    statusBox.classList.remove("d-none");
  }

  button.addEventListener("click", function () {
    if (busy) return;
    if (modal) { modal.show(); } else if (window.confirm("Send an emergency alert to your contacts?")) { sendAlert(); }
  });

  confirmBtn.addEventListener("click", function () {
    if (modal) modal.hide();
    sendAlert();
  });

  function setBusy(isBusy) {
    busy = isBusy;
    button.disabled = isBusy;
    button.setAttribute("aria-busy", isBusy ? "true" : "false");
  }

  function sendAlert() {
    if (busy) return;
    setBusy(true);
    show("info", '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Getting your location...');

    SWS.getLocation({ timeout: 15000 }).then(function (pos) {
      var lat = SWS.round6(pos.latitude), lon = SWS.round6(pos.longitude);
      SWS.showMap("sos-map", lat, lon, pos.accuracy);
      show("info", '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Location found. Sending alert...');
      return SWS.postJSON(url, { latitude: lat, longitude: lon, accuracy: pos.accuracy }).then(function (res) {
        if (res.status === 401) {
          show("danger", "Your session expired. <a href='/login/'>Log in again</a> and retry.");
          return;
        }
        if (!res.data.ok) {
          show("danger", "<strong>Alert not sent.</strong> " + SWS.escapeHtml(res.data.error || "Please try again."));
          return;
        }
        renderSuccess(res.data);
      });
    }).catch(function (err) {
      if (err && err.code) {
        show("danger", "<strong>Alert not sent.</strong> " + SWS.escapeHtml(err.message) +
          ' <button type="button" class="btn btn-sm btn-outline-danger ms-2" id="sos-retry">Try again</button>');
        var retry = document.getElementById("sos-retry");
        if (retry) retry.addEventListener("click", sendAlert);
      } else {
        show("danger", "<strong>Alert not sent.</strong> The server could not be reached. You may be offline. Please try again.");
      }
    }).then(function () { setBusy(false); });
  }

  function renderSuccess(d) {
    var level = d.status === "NOTIFIED" ? "success" : "warning";
    var summary;
    if (d.contacts_total === 0) {
      summary = "The alert was saved, but you have no emergency contacts to notify. Add contacts on the Emergency Contacts page.";
    } else if (d.status === "NOTIFIED") {
      summary = "Your emergency contacts were notified (" + d.contacts_notified + " of " + d.contacts_total + ").";
    } else {
      summary = "The alert was saved, but notifying your contacts failed. Please contact someone directly.";
    }
    show(level,
      "<h2 class='h5 mb-2'>Emergency alert created</h2>" +
      "<p class='mb-2'>" + SWS.escapeHtml(summary) + "</p>" +
      "<p class='mb-2'><strong>Location:</strong> " + SWS.escapeHtml(d.latitude) + ", " + SWS.escapeHtml(d.longitude) +
      " &middot; <a href='" + SWS.escapeHtml(d.map_link) + "' target='_blank' rel='noopener'>Open map link</a></p>" +
      "<p class='small text-muted mb-0'>Academic prototype: this does not contact police or emergency services. " +
      "If you are in danger, call your local emergency number now.</p>");
  }
})();
