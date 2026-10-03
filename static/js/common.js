/* Shared helpers: CSRF, JSON requests, geolocation with friendly errors, Leaflet map. */
(function () {
  "use strict";

  function getCookie(name) {
    var parts = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < parts.length; i++) {
      var pair = parts[i].split("=");
      if (pair[0] === name) return decodeURIComponent(pair.slice(1).join("="));
    }
    return "";
  }

  // POST JSON with the CSRF token. Resolves {status, data}; rejects only on network failure.
  function postJSON(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(payload || {})
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        return { status: response.status, data: data };
      });
    });
  }

  function getJSON(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          return { status: response.status, data: data };
        });
      });
  }

  var GEO_MESSAGES = {
    UNSUPPORTED: "Your browser does not support location services. Try a recent version of Chrome, Edge or Firefox.",
    OFFLINE: "You appear to be offline. Connect to the internet and try again.",
    PERMISSION_DENIED: "Location permission was denied. Click the lock icon in the address bar, allow Location for this site, then try again.",
    POSITION_UNAVAILABLE: "Your location is currently unavailable. Check that GPS/location services are turned on and try again.",
    TIMEOUT: "Finding your location took too long. Move to an open area or check your connection, then try again."
  };

  // Resolves {latitude, longitude, accuracy}; rejects {code, message}.
  function getLocation(options) {
    return new Promise(function (resolve, reject) {
      if (!("geolocation" in navigator)) {
        return reject({ code: "UNSUPPORTED", message: GEO_MESSAGES.UNSUPPORTED });
      }
      if (navigator.onLine === false) {
        return reject({ code: "OFFLINE", message: GEO_MESSAGES.OFFLINE });
      }
      var opts = Object.assign({ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }, options || {});
      navigator.geolocation.getCurrentPosition(
        function (position) {
          resolve({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy
          });
        },
        function (error) {
          var code = { 1: "PERMISSION_DENIED", 2: "POSITION_UNAVAILABLE", 3: "TIMEOUT" }[error.code] || "POSITION_UNAVAILABLE";
          reject({ code: code, message: GEO_MESSAGES[code] });
        },
        opts
      );
    });
  }

  function round6(n) { return Math.round(n * 1e6) / 1e6; }

  function mapLink(lat, lon) {
    return "https://www.google.com/maps?q=" + lat + "," + lon;
  }

  // Draw (or update) a Leaflet/OpenStreetMap map inside the element with this id.
  function showMap(elementId, lat, lon, accuracy) {
    var el = document.getElementById(elementId);
    if (!el) return;
    if (typeof L === "undefined") {
      el.innerHTML = '<div class="p-3 text-muted small">The map library could not be loaded (check your internet connection). ' +
        'Your coordinates are shown above and the map link still works.</div>';
      return;
    }
    el.classList.remove("d-none");
    if (!el._map) {
      el._map = L.map(el);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(el._map);
    }
    var map = el._map;
    if (el._marker) map.removeLayer(el._marker);
    if (el._circle) map.removeLayer(el._circle);
    el._marker = L.marker([lat, lon]).addTo(map).bindPopup("You are here").openPopup();
    if (accuracy && accuracy > 0) {
      el._circle = L.circle([lat, lon], { radius: accuracy, weight: 1, fillOpacity: 0.1 }).addTo(map);
    }
    map.setView([lat, lon], 16);
    setTimeout(function () { map.invalidateSize(); }, 200);
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  window.SWS = {
    getCookie: getCookie, postJSON: postJSON, getJSON: getJSON, getLocation: getLocation,
    showMap: showMap, mapLink: mapLink, round6: round6, escapeHtml: escapeHtml
  };
})();
