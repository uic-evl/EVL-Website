// Renders the service list from status.json in this folder.
// Edit status.json to change what is shown; no build step is needed.

(function () {
  const tbody = document.querySelector("#services tbody");
  const updated = document.getElementById("updated");

  function escape(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function render(data) {
    const services = Array.isArray(data.services) ? data.services : [];
    if (services.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="loading">No services listed.</td></tr>';
    } else {
      tbody.innerHTML = services.map(function (s) {
        const status = (s.status || "unknown").toLowerCase();
        return "<tr>" +
          "<td>" + escape(s.name) + "</td>" +
          '<td><span class="badge ' + escape(status) + '">' + escape(status) + "</span></td>" +
          "<td>" + escape(s.note) + "</td>" +
          "</tr>";
      }).join("");
    }
    updated.textContent = data.updated || "unknown";
  }

  fetch("status.json", { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(render)
    .catch(function (err) {
      tbody.innerHTML = '<tr><td colspan="3" class="loading">Could not load status.json (' + escape(err.message) + ").</td></tr>";
    });
})();
