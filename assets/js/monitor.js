// Server monitor (/internal/monitor/): one row per server, expand a row for details.
// Data comes from the monitor hub on arcade, which polls each server's agent and lists the
// servers: https://arcade.evl.uic.edu/stats/overview.json and /stats/<id>/<file>
// (github.com/uic-evl/evl-monitoring). Class names are written out in full so the site's
// PurgeCSS keeps them.
(function () {
  "use strict";

  var STATE_CLASSES = ["mon-state-loading", "mon-state-live", "mon-state-stale", "mon-state-offline", "mon-state-planned"];
  var STATE_CLASS = {
    loading: "mon-state-loading",
    live: "mon-state-live",
    stale: "mon-state-stale",
    offline: "mon-state-offline",
    planned: "mon-state-planned",
  };
  var RANGES = ["1h", "24h", "7d", "30d", "1y"];
  var RANGE_LABEL = { "1h": "1 hour", "24h": "24 hours", "7d": "7 days", "30d": "30 days", "1y": "1 year" };
  var FETCH_TIMEOUT = 8000;
  var BACKOFF = [5, 10, 20, 40, 60];

  var cfg = null;
  var base = "";
  var hosts = []; // in the hub's order
  var rows = {}; // by id
  var rowOrder = "";
  var charts = [];
  var hidden = false;

  // helpers -------------------------------------------------------------------

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function svg(tag, attrs) {
    var n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) {
      n.setAttribute(k, attrs[k]);
    });
    return n;
  }

  function clear(n) {
    while (n.firstChild) n.removeChild(n.firstChild);
    return n;
  }

  function num(v) {
    return typeof v === "number" && isFinite(v);
  }

  function pct(v) {
    return num(v) ? Math.round(v) + "%" : "n/a";
  }

  function gib(v) {
    if (!num(v)) return "n/a";
    if (v >= 1024) return (v / 1024).toFixed(1) + " TiB";
    return (v >= 10 ? Math.round(v) : v.toFixed(1)) + " GiB";
  }

  function pair(used, total, unit) {
    if (!num(used) || !num(total)) return "n/a";
    var big = total >= 1024 && unit === "GiB";
    var d = big ? 1024 : 1;
    var u = big ? "TiB" : unit;
    var fmt = function (x) {
      x = x / d;
      return x >= 10 ? String(Math.round(x)) : x.toFixed(1);
    };
    return fmt(used) + " / " + fmt(total) + " " + u;
  }

  function rate(v) {
    if (!num(v)) return "n/a";
    if (v >= 1000) return (v / 1000).toFixed(1) + " GB/s";
    return (v >= 10 ? Math.round(v) : v.toFixed(1)) + " MB/s";
  }

  function duration(s) {
    if (!num(s) || s < 0) return "n/a";
    var d = Math.floor(s / 86400);
    var h = Math.floor((s % 86400) / 3600);
    if (d > 0) return d + (d === 1 ? " day " : " days ") + h + " h";
    var m = Math.floor((s % 3600) / 60);
    return h > 0 ? h + " h " + m + " min" : m + " min";
  }

  var clockFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
  var timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
  var dayFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
  var weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short" });
  var monthFmt = new Intl.DateTimeFormat(undefined, { month: "short" });
  var fullFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

  function cssVar(name) {
    return getComputedStyle(document.getElementById("evl-monitor")).getPropertyValue(name).trim();
  }

  function seriesColor(i) {
    return cssVar("--mon-s" + ((i % 8) + 1));
  }

  // data ----------------------------------------------------------------------

  function dataBase() {
    var b = cfg.data_base || "https://arcade.evl.uic.edu/stats";
    var local = location.hostname === "localhost" || location.hostname === "127.0.0.1";
    var q = new URLSearchParams(location.search).get("data");
    if (local && q) b = q;
    return b.replace(/\/$/, "");
  }

  function getJSON(h, file, signal) {
    var ctl = new AbortController();
    var timer = setTimeout(function () {
      ctl.abort();
    }, FETCH_TIMEOUT);
    if (signal) {
      signal.addEventListener("abort", function () {
        ctl.abort();
      });
    }
    return fetch(base + "/" + h.id + "/" + file, { cache: "no-cache", credentials: "omit", signal: ctl.signal })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        var date = r.headers.get("Date");
        return r.json().then(function (j) {
          if (!j || j.v !== 1 || j.id !== h.id) throw new Error("unexpected payload");
          return { json: j, date: date ? Date.parse(date) : null };
        });
      })
      .finally(function () {
        clearTimeout(timer);
      });
  }

  // rows ------------------------------------------------------------------------

  function makeRow(x) {
    var section = el("section", "mon-server mon-state-loading");
    section.setAttribute("data-id", x.id);
    var button = el("button", "mon-row");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", "mon-detail-" + x.id);
    var name = el("span", "mon-name");
    var nameText = el("strong");
    var groupText = el("small");
    name.appendChild(nameText);
    name.appendChild(groupText);
    button.appendChild(name);
    var status = el("span", "mon-status");
    var dot = el("i", "mon-dot");
    dot.setAttribute("aria-hidden", "true");
    var statusText = el("span", "mon-status-text", "Connecting");
    status.appendChild(dot);
    status.appendChild(statusText);
    button.appendChild(status);
    var cells = {};
    [["cpu", "mon-cell mon-cpu", "CPU"], ["mem", "mon-cell mon-mem", "Memory"], ["gpu", "mon-cell mon-gpu", "GPUs"], ["d30", "mon-cell mon-30d", "Last 30 days"]].forEach(function (c) {
      var cell = el("span", c[1]);
      cell.setAttribute("data-label", c[2]);
      cells[c[0]] = cell;
      button.appendChild(cell);
    });
    var chev = el("i", "mon-chev");
    chev.setAttribute("aria-hidden", "true");
    button.appendChild(chev);
    var detailEl = el("div", "mon-detail");
    detailEl.id = "mon-detail-" + x.id;
    detailEl.hidden = true;
    section.appendChild(button);
    section.appendChild(detailEl);
    var h = {
      id: x.id,
      status: null, // live or planned, from hosts.yml through the hub
      spec: null,
      section: section,
      button: button,
      detailEl: detailEl,
      statusText: statusText,
      nameText: nameText,
      groupText: groupText,
      cells: cells,
      state: "loading",
      failures: 0,
      now: null,
      detail: null,
    };
    button.addEventListener("click", function () {
      if (h.status !== "live") return;
      if (h.detail && h.detail.open) closeDetail(h);
      else openDetail(h);
    });
    return h;
  }

  // what hosts.yml says about the hardware, until the server reports
  function showSpec(h, x) {
    [["cpu", x.cpus], ["mem", x.memory], ["gpu", x.gpus]].forEach(function (c) {
      var cell = clear(h.cells[c[0]]);
      if (!c[1]) return;
      var v = el("span", "mon-value mon-muted", c[1]);
      v.title = c[1];
      cell.appendChild(v);
    });
  }

  function configure(h, x) {
    h.nameText.textContent = x.name || x.id;
    h.groupText.textContent = x.group || "";
    var status = x.status === "planned" ? "planned" : "live";
    var spec = [x.cpus, x.memory, x.gpus].join("|");
    if (status === h.status && spec === h.spec) return;
    h.status = status;
    h.spec = spec;
    h.button.disabled = status !== "live";
    if (status === "planned") {
      closeDetail(h);
      h.now = null;
      h.daily = null;
      clear(h.cells.d30);
      showSpec(h, x);
      setState(h, "planned", "Not reporting yet");
    } else if (!h.now) {
      showSpec(h, x);
    }
  }

  // one row per server in the overview, in its order; rows for removed servers go away
  function syncRows(list) {
    var seen = {};
    list.forEach(function (x) {
      seen[x.id] = true;
      if (!rows[x.id]) rows[x.id] = makeRow(x);
      configure(rows[x.id], x);
    });
    hosts.forEach(function (h) {
      if (seen[h.id]) return;
      closeDetail(h);
      h.section.remove();
      delete rows[h.id];
    });
    hosts = list.map(function (x) {
      return rows[x.id];
    });
    document.getElementById("mon-head").hidden = !hosts.length;
    var order = list.map(function (x) {
      return x.id;
    }).join(",");
    if (order !== rowOrder) {
      var box = document.getElementById("mon-list");
      hosts.forEach(function (h) {
        box.appendChild(h.section);
      });
      rowOrder = order;
    }
  }

  function setState(h, state, text) {
    h.state = state;
    STATE_CLASSES.forEach(function (c) {
      h.section.classList.remove(c);
    });
    h.section.classList.add(STATE_CLASS[state]);
    h.statusText.textContent = text;
    updateSummary();
  }

  function meterCell(cell, label, fraction) {
    clear(cell);
    cell.appendChild(el("span", "mon-value", label));
    var m = el("span", "mon-meter");
    var i = el("i");
    i.style.width = num(fraction) ? Math.max(0, Math.min(100, fraction)) + "%" : "0";
    m.appendChild(i);
    cell.appendChild(m);
  }

  function renderRow(h) {
    var n = h.now;
    if (!n) return;
    var host = n.host || {};
    meterCell(h.cells.cpu, pct(host.cpu_pct) + (num(host.load1) ? ", load " + host.load1.toFixed(1) : ""), host.cpu_pct);
    meterCell(h.cells.mem, pair(host.mem_used_gib, host.mem_total_gib, "GiB"), host.mem_pct);

    var cell = clear(h.cells.gpu);
    var gpus = n.gpus || [];
    if (!gpus.length) {
      cell.appendChild(el("span", "mon-value mon-muted", n.gpu_status === "disabled" || n.gpu_status === "absent" ? "No GPUs" : "GPU data unavailable"));
      return;
    }
    if (n.gpu_status !== "ok") {
      cell.appendChild(el("span", "mon-value mon-muted", "GPU data unavailable"));
      return;
    }
    var utils = gpus.map(function (g) {
      return g.util_pct;
    }).filter(num);
    var avg = utils.length ? utils.reduce(function (a, b) {
      return a + b;
    }, 0) / utils.length : null;
    var memUsed = 0;
    var memTotal = 0;
    gpus.forEach(function (g) {
      if (num(g.mem_used_gib)) memUsed += g.mem_used_gib;
      if (num(g.mem_total_gib)) memTotal += g.mem_total_gib;
    });
    var memPct = memTotal ? (memUsed / memTotal) * 100 : null;
    var summary = el("span", "mon-value", (num(avg) ? pct(avg) + " use, " : "") + pct(memPct) + " mem");
    summary.title = gpus.length + (gpus.length === 1 ? " GPU, " : " GPUs, ") + pair(memUsed, memTotal, "GiB") + " memory in use";
    cell.appendChild(summary);
    var bars = el("span", "mon-gpubars");
    bars.setAttribute("aria-hidden", "true");
    gpus.forEach(function (g) {
      var b = el("i");
      if (num(g.util_pct)) {
        b.style.height = Math.max(4, g.util_pct) + "%";
      } else {
        b.className = "mon-none";
      }
      b.title = "GPU " + g.i + ": " + pct(g.util_pct) + " use";
      bars.appendChild(b);
    });
    cell.appendChild(bars);
  }

  function renderDailyCell(h) {
    var cell = clear(h.cells.d30);
    var days = (h.daily && h.daily.days) || [];
    var vals = days.map(function (d) {
      return d.load_pct;
    });
    var have = vals.filter(num);
    if (!have.length) return;
    var avg = have.reduce(function (a, b) {
      return a + b;
    }, 0) / have.length;
    cell.appendChild(el("span", "mon-value", pct(avg) + " average load"));
    var w = 100;
    var hgt = 24;
    var bw = w / Math.max(days.length, 1);
    var s = svg("svg", { class: "mon-spark", viewBox: "0 0 " + w + " " + hgt, preserveAspectRatio: "none", role: "img" });
    s.setAttribute("aria-label", "Average daily load over the last " + days.length + " days");
    days.forEach(function (d, i) {
      if (!num(d.load_pct)) return;
      var bh = Math.max(1, (d.load_pct / 100) * hgt);
      var r = svg("rect", { x: (i * bw + bw * 0.12).toFixed(2), y: (hgt - bh).toFixed(2), width: (bw * 0.76).toFixed(2), height: bh.toFixed(2), rx: "0.6" });
      var t = svg("title");
      t.textContent = d.date + ": load " + pct(d.load_pct);
      r.appendChild(t);
      s.appendChild(r);
    });
    cell.appendChild(s);
  }

  function updateSummary() {
    var live = hosts.filter(function (h) {
      return h.status === "live";
    });
    var reporting = live.filter(function (h) {
      return h.state === "live";
    }).length;
    var planned = hosts.length - live.length;
    var text = reporting + " of " + live.length + " servers reporting";
    if (planned) text += ", " + planned + " not online yet";
    text += ". Updated " + clockFmt.format(new Date()) + ".";
    document.getElementById("mon-summary").textContent = text;
  }

  // overview polling: one request, for every server, from the hub ----------------

  var overviewTimer = null;
  var overviewCtl = null;
  var overviewFailures = 0;
  var overviewSeen = false;

  function scheduleOverview(ms) {
    clearTimeout(overviewTimer);
    if (hidden) return;
    overviewTimer = setTimeout(pollOverview, ms);
  }

  function applyHost(h, x) {
    var newDaily = x.daily && (!h.daily || x.daily.ts !== h.daily.ts);
    if (x.now) h.now = x.now;
    if (x.daily) h.daily = x.daily;
    if (x.last_ok) h.lastSeen = x.last_ok;
    if (h.now) renderRow(h);
    if (newDaily) {
      renderDailyCell(h);
      if (h.detail && h.detail.open) renderDailyChart(h);
    }
    if (x.status === "live") {
      setState(h, "live", "Live");
    } else if (x.status === "stale") {
      setState(h, "stale", "Stale, " + duration(x.age_s));
    } else if (x.status === "offline") {
      setState(h, "offline", h.lastSeen ? "Offline since " + timeFmt.format(new Date(h.lastSeen * 1000)) : "Offline");
    } else {
      setState(h, "loading", "Connecting");
    }
  }

  function pollOverview() {
    if (overviewCtl) overviewCtl.abort();
    var ctl = new AbortController();
    overviewCtl = ctl;
    var timer = setTimeout(function () {
      ctl.abort();
    }, FETCH_TIMEOUT);
    fetch(base + "/overview.json", { cache: "no-cache", credentials: "omit", signal: ctl.signal })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (o) {
        if (!o || o.v !== 1 || !Array.isArray(o.hosts)) throw new Error("unexpected payload");
        overviewFailures = 0;
        overviewSeen = true;
        document.getElementById("mon-banner").hidden = true;
        syncRows(o.hosts);
        o.hosts.forEach(function (x) {
          if (rows[x.id].status === "live") applyHost(rows[x.id], x);
        });
        updateSummary();
        scheduleOverview((o.now_seconds || 15) * 1000 + Math.random() * 1000);
      })
      .catch(function () {
        if (ctl.signal.aborted && hidden) return;
        overviewFailures += 1;
        if (!overviewSeen || overviewFailures >= 2) {
          document.getElementById("mon-banner").hidden = false;
          hosts.forEach(function (h) {
            if (h.status === "live") setState(h, h.now ? "stale" : "offline", "No data");
          });
          if (!overviewSeen) document.getElementById("mon-summary").textContent = "No data.";
        }
        scheduleOverview(BACKOFF[Math.min(overviewFailures - 1, BACKOFF.length - 1)] * 1000);
      })
      .finally(function () {
        clearTimeout(timer);
      });
  }

  // charts ----------------------------------------------------------------------

  function chartTheme() {
    return {
      ink: cssVar("--global-text-color") || "#1b1b1f",
      muted: cssVar("--global-text-color-light") || "#5c5c66",
      grid: cssVar("--global-divider-color") || "rgba(0,0,0,0.08)",
      card: cssVar("--global-card-bg-color") || "#ffffff",
    };
  }

  function tickStep(range) {
    return { "1h": 10 * 60e3, "24h": 3 * 3600e3, "7d": 86400e3, "30d": 5 * 86400e3, "1y": 0 }[range];
  }

  function makeTicks(min, max, range) {
    var out = [];
    var d = new Date(min);
    if (range === "1y") {
      d = new Date(d.getFullYear(), d.getMonth() + 1, 1);
      while (d.getTime() <= max) {
        out.push(d.getTime());
        d = new Date(d.getFullYear(), d.getMonth() + 1, 1);
      }
      return out;
    }
    if (range === "1h") {
      d.setSeconds(0, 0);
      d.setMinutes(Math.ceil(d.getMinutes() / 10) * 10);
    } else if (range === "24h") {
      d.setMinutes(0, 0, 0);
      d.setHours(Math.ceil(d.getHours() / 3) * 3);
    } else {
      d.setHours(24, 0, 0, 0);
    }
    var step = tickStep(range);
    var k = 0;
    while (d.getTime() <= max && k < 60) {
      out.push(d.getTime());
      if (range === "7d" || range === "30d") {
        d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + (range === "7d" ? 1 : 5));
      } else {
        d = new Date(d.getTime() + step);
      }
      k++;
    }
    return out;
  }

  function tickLabel(v, range) {
    var d = new Date(v);
    if (range === "1h" || range === "24h") return timeFmt.format(d);
    if (range === "7d") return weekdayFmt.format(d);
    if (range === "30d") return dayFmt.format(d);
    return monthFmt.format(d);
  }

  function lineChart(canvas, unit, maxY) {
    var st = { range: "24h" };
    var th = chartTheme();
    var c = new window.Chart(canvas, {
      type: "line",
      data: { datasets: [] },
      options: {
        parsing: false,
        normalized: true,
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        spanGaps: false,
        interaction: { mode: "index", intersect: false },
        elements: { point: { radius: 0, hoverRadius: 4, hitRadius: 6 }, line: { borderWidth: 2, tension: 0 } },
        plugins: {
          legend: {
            position: "bottom",
            align: "start",
            labels: { boxWidth: 10, boxHeight: 10, color: th.muted, font: { size: 11 } },
          },
          decimation: { enabled: true, algorithm: "min-max" },
          tooltip: {
            backgroundColor: th.card,
            titleColor: th.ink,
            bodyColor: th.ink,
            borderColor: th.grid,
            borderWidth: 1,
            callbacks: {
              title: function (items) {
                return items.length ? fullFmt.format(new Date(items[0].parsed.x)) : "";
              },
              label: function (item) {
                var v = item.parsed.y;
                return " " + item.dataset.label + ": " + (num(v) ? (unit === "%" ? v.toFixed(1) + "%" : v.toFixed(1) + " " + unit) : "n/a");
              },
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            grid: { display: false },
            border: { color: th.grid },
            ticks: {
              color: th.muted,
              font: { size: 11 },
              maxRotation: 0,
              autoSkip: true,
              callback: function (v) {
                return tickLabel(v, st.range);
              },
            },
            afterBuildTicks: function (axis) {
              axis.ticks = makeTicks(axis.min, axis.max, st.range).map(function (v) {
                return { value: v };
              });
            },
          },
          y: {
            min: 0,
            max: maxY,
            border: { display: false },
            grid: { color: th.grid },
            ticks: { color: th.muted, font: { size: 11 }, maxTicksLimit: 5 },
          },
        },
      },
    });
    c.$st = st;
    charts.push(c);
    return c;
  }

  function setLine(c, hist, series, range) {
    var xs = [];
    for (var i = 0; i < hist.n; i++) xs.push((hist.start + i * hist.step) * 1000);
    c.$st.range = range;
    c.data.datasets = series.map(function (s) {
      return {
        label: s.label,
        data: (s.values || []).map(function (y, i) {
          return { x: xs[i], y: num(y) ? y : null };
        }),
        borderColor: s.color,
        backgroundColor: s.color,
        $slot: s.slot,
      };
    });
    c.options.scales.x.min = hist.start * 1000;
    c.options.scales.x.max = (hist.start + hist.n * hist.step) * 1000;
    c.options.plugins.legend.display = series.length > 1;
    c.update("none");
  }

  function retheme() {
    var th = chartTheme();
    charts.forEach(function (c) {
      var o = c.options;
      if (o.plugins.legend) o.plugins.legend.labels.color = th.muted;
      if (o.plugins.tooltip) {
        o.plugins.tooltip.backgroundColor = th.card;
        o.plugins.tooltip.titleColor = th.ink;
        o.plugins.tooltip.bodyColor = th.ink;
        o.plugins.tooltip.borderColor = th.grid;
      }
      ["x", "y"].forEach(function (a) {
        if (!o.scales[a]) return;
        o.scales[a].ticks.color = th.muted;
        if (o.scales[a].grid && o.scales[a].grid.color) o.scales[a].grid.color = th.grid;
        if (o.scales[a].border) o.scales[a].border.color = th.grid;
      });
      c.data.datasets.forEach(function (ds) {
        if (ds.$slot !== undefined) {
          ds.borderColor = seriesColor(ds.$slot);
          ds.backgroundColor = seriesColor(ds.$slot);
        }
      });
      c.update("none");
    });
  }

  // detail ----------------------------------------------------------------------

  function fig(caption, wide) {
    var f = el("figure", "mon-fig");
    f.appendChild(el("figcaption", null, caption));
    var box = el("div", wide ? "mon-chart mon-chart-wide" : "mon-chart");
    var canvas = el("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", caption);
    box.appendChild(canvas);
    f.appendChild(box);
    return { fig: f, canvas: canvas };
  }

  function buildDetail(h) {
    var root = clear(h.detailEl);
    var d = {
      open: false,
      range: "24h",
      facts: el("p", "mon-facts", "Loading."),
      ranges: el("div", "mon-ranges"),
      chartsBox: el("div", "mon-charts"),
      gpuBox: el("div"),
      dailyBox: el("div"),
      modelsBox: el("div"),
      routesBox: el("div"),
      containersBox: el("div"),
      storageBox: el("div"),
      timers: [],
      charts: {},
    };
    h.detail = d;
    root.appendChild(d.facts);

    d.ranges.setAttribute("role", "group");
    d.ranges.setAttribute("aria-label", "History range");
    RANGES.forEach(function (r) {
      var b = el("button", null, r);
      b.type = "button";
      b.title = RANGE_LABEL[r];
      b.setAttribute("aria-pressed", r === d.range ? "true" : "false");
      b.addEventListener("click", function () {
        d.range = r;
        Array.prototype.forEach.call(d.ranges.children, function (x) {
          x.setAttribute("aria-pressed", x === b ? "true" : "false");
        });
        loadHistory(h);
      });
      d.ranges.appendChild(b);
    });
    root.appendChild(d.ranges);

    var specs = [
      ["cpumem", "CPU and memory (%)", "%", 100],
      ["gpuutil", "GPU utilization (%)", "%", 100],
      ["gpumem", "GPU memory (%)", "%", 100],
      ["gpupower", "GPU power (W)", "W", undefined],
      ["net", "Network (MB/s)", "MB/s", undefined],
      ["disk", "Disk (MB/s)", "MB/s", undefined],
    ];
    specs.forEach(function (s) {
      var f = fig(s[1]);
      d.chartsBox.appendChild(f.fig);
      d.charts[s[0]] = { fig: f.fig, canvas: f.canvas, unit: s[2], max: s[3], chart: null };
    });
    root.appendChild(d.chartsBox);

    [["GPUs", d.gpuBox], ["Last 30 days", d.dailyBox], ["Models", d.modelsBox],
      ["Web services", d.routesBox], ["Containers", d.containersBox], ["Storage", d.storageBox]].forEach(function (s) {
      root.appendChild(el("h3", null, s[0]));
      root.appendChild(s[1]);
    });
  }

  function chartFor(h, key) {
    var c = h.detail.charts[key];
    if (!c.chart) c.chart = lineChart(c.canvas, c.unit, c.max);
    return c.chart;
  }

  function loadHistory(h) {
    var d = h.detail;
    var range = d.range;
    getJSON(h, "history/" + range + ".json")
      .then(function (res) {
        if (range !== d.range || !window.Chart) return;
        var hist = res.json;
        var host = hist.host || {};
        var get = function (k) {
          return host[k] ? host[k].mean : [];
        };
        setLine(chartFor(h, "cpumem"), hist, [
          { label: "CPU", values: get("cpu_pct"), color: seriesColor(0), slot: 0 },
          { label: "Memory", values: get("mem_pct"), color: seriesColor(1), slot: 1 },
        ], range);
        setLine(chartFor(h, "net"), hist, [
          { label: "Received", values: get("net_rx_mbs"), color: seriesColor(0), slot: 0 },
          { label: "Sent", values: get("net_tx_mbs"), color: seriesColor(1), slot: 1 },
        ], range);
        setLine(chartFor(h, "disk"), hist, [
          { label: "Read", values: get("disk_r_mbs"), color: seriesColor(0), slot: 0 },
          { label: "Write", values: get("disk_w_mbs"), color: seriesColor(1), slot: 1 },
        ], range);
        var gpus = hist.gpus || [];
        ["gpuutil", "gpumem", "gpupower"].forEach(function (key) {
          d.charts[key].fig.hidden = !gpus.length;
        });
        if (gpus.length) {
          var per = function (metric) {
            return gpus.map(function (g) {
              return { label: "GPU " + g.i, values: g[metric] ? g[metric].mean : [], color: seriesColor(g.i), slot: g.i };
            });
          };
          setLine(chartFor(h, "gpuutil"), hist, per("util_pct"), range);
          setLine(chartFor(h, "gpumem"), hist, per("mem_pct"), range);
          setLine(chartFor(h, "gpupower"), hist, per("power_w"), range);
        }
      })
      .catch(function () {});
  }

  function table(headers) {
    var wrap = el("div", "mon-table-wrap");
    var t = el("table", "mon-table");
    var tr = el("tr");
    headers.forEach(function (x) {
      tr.appendChild(el("th", null, x));
    });
    var thead = el("thead");
    thead.appendChild(tr);
    t.appendChild(thead);
    var tbody = el("tbody");
    t.appendChild(tbody);
    wrap.appendChild(t);
    return { wrap: wrap, body: tbody };
  }

  function td(text, cls) {
    return el("td", cls, text);
  }

  function renderFacts(h, host) {
    var f = host.facts || {};
    var cpu = host.cpu || {};
    var parts = [];
    if (f.os) parts.push(f.os);
    if (f.kernel) parts.push("kernel " + f.kernel);
    if (f.cpu_model) {
      var topo = [];
      if (cpu.sockets && cpu.sockets > 1) topo.push(cpu.sockets + " sockets");
      if (cpu.cores) topo.push(cpu.cores + " cores");
      if (cpu.threads) topo.push(cpu.threads + " threads");
      parts.push(f.cpu_model + (topo.length ? " (" + topo.join(", ") + ")" : ""));
    }
    if (host.mem && num(host.mem.total_gib)) parts.push(gib(host.mem.total_gib) + " RAM");
    if (f.gpu_driver) parts.push("NVIDIA driver " + f.gpu_driver + (f.cuda ? ", CUDA " + f.cuda : ""));
    if (num(host.boot_ts)) parts.push("up " + duration(Date.now() / 1000 - host.boot_ts));
    h.detail.facts.textContent = parts.join(" · ");
  }

  function renderGpus(h, procs) {
    var box = clear(h.detail.gpuBox);
    var n = h.now || {};
    var gpus = n.gpus || [];
    if (!gpus.length) {
      box.appendChild(el("p", "mon-note", n.gpu_status === "ok" ? "No GPUs." : "No GPU data from this server."));
      return;
    }
    var names = {};
    ((h.host && h.host.gpus) || []).forEach(function (g) {
      names[g.i] = g.name;
    });
    var byGpu = {};
    ((procs && procs.gpus) || []).forEach(function (g) {
      byGpu[g.i] = g;
    });
    var t = table(["GPU", "Use", "Memory", "Power", "Temp", "Processes"]);
    gpus.forEach(function (g) {
      var tr = el("tr");
      var first = el("td");
      var key = el("span", "mon-key");
      key.style.background = seriesColor(g.i);
      first.appendChild(key);
      first.appendChild(document.createTextNode("GPU " + g.i));
      if (names[g.i]) first.appendChild(el("span", "mon-proc mon-muted", names[g.i]));
      (g.throttle || []).forEach(function (r) {
        if (r !== "gpu_idle") first.appendChild(el("span", "mon-badge", r.replace(/_/g, " ")));
      });
      if (g.mig) first.appendChild(el("span", "mon-badge", "MIG"));
      tr.appendChild(first);

      var use = el("td");
      use.appendChild(el("span", "mon-value", pct(g.util_pct)));
      var m = el("span", "mon-meter");
      var fill = el("i");
      fill.style.width = num(g.util_pct) ? g.util_pct + "%" : "0";
      m.appendChild(fill);
      use.appendChild(m);
      tr.appendChild(use);

      tr.appendChild(td(pair(g.mem_used_gib, g.mem_total_gib, "GiB")));
      tr.appendChild(td(num(g.power_w) ? Math.round(g.power_w) + (num(g.power_limit_w) ? " / " + Math.round(g.power_limit_w) : "") + " W" : "n/a"));
      tr.appendChild(td(num(g.temp_c) ? Math.round(g.temp_c) + " °C" : "n/a"));

      var cell = el("td");
      var p = byGpu[g.i];
      if (!procs || procs.procs_status !== "ok") {
        cell.appendChild(el("span", "mon-muted", num(g.procs) ? g.procs + (g.procs === 1 ? " process" : " processes") : "n/a"));
      } else if (!p || !p.procs.length) {
        cell.appendChild(el("span", "mon-muted", "idle"));
      } else {
        p.procs.slice(0, 5).forEach(function (x) {
          var who = x.user + (x.container ? " in " + x.container : "") + (x.name ? ", " + x.name : "");
          cell.appendChild(el("span", "mon-proc", who + (num(x.mem_gib) ? " (" + gib(x.mem_gib) + ")" : "")));
        });
        var more = p.procs.length - 5 + (p.more || 0);
        if (more > 0) cell.appendChild(el("span", "mon-proc mon-muted", more + " more"));
      }
      tr.appendChild(cell);
      t.body.appendChild(tr);
    });
    box.appendChild(t.wrap);
  }

  function renderDailyChart(h) {
    var d = h.detail;
    var box = d.dailyBox;
    var days = (h.daily && h.daily.days) || [];
    if (!days.length || !window.Chart) {
      clear(box).appendChild(el("p", "mon-note", "No daily data yet."));
      d.dailyChart = null;
      return;
    }
    if (!d.dailyChart) {
      clear(box);
      var f = fig("Average load per day (%)", true);
      box.appendChild(f.fig);
      box.appendChild(el("p", "mon-note", "Each day is the average of CPU, memory, GPU utilization and GPU memory use. Hover a day for the parts."));
      var th = chartTheme();
      d.dailyChart = new window.Chart(f.canvas, {
        type: "bar",
        data: { labels: [], datasets: [{ label: "Load", data: [], $slot: 0, maxBarThickness: 24, borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom" }] },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: th.card,
              titleColor: th.ink,
              bodyColor: th.ink,
              borderColor: th.grid,
              borderWidth: 1,
              callbacks: {
                label: function (item) {
                  var x = d.dailyChart.$days[item.dataIndex];
                  var lines = [" Load: " + pct(x.load_pct), " CPU: " + pct(x.cpu_pct), " Memory: " + pct(x.mem_pct)];
                  if (num(x.gpu_util_pct)) lines.push(" GPU use: " + pct(x.gpu_util_pct), " GPU memory: " + pct(x.gpu_mem_pct));
                  if (x.hours < 23) lines.push(" " + x.hours + " h of data");
                  return lines;
                },
              },
            },
          },
          scales: {
            x: { grid: { display: false }, border: { color: th.grid }, ticks: { color: th.muted, font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
            y: { min: 0, max: 100, border: { display: false }, grid: { color: th.grid }, ticks: { color: th.muted, font: { size: 11 }, maxTicksLimit: 5 } },
          },
        },
      });
      charts.push(d.dailyChart);
    }
    var c = d.dailyChart;
    c.$days = days;
    c.data.labels = days.map(function (x) {
      return dayFmt.format(new Date(x.day * 1000));
    });
    c.data.datasets[0].data = days.map(function (x) {
      return num(x.load_pct) ? x.load_pct : null;
    });
    c.data.datasets[0].backgroundColor = seriesColor(0);
    c.update("none");
  }

  function renderServices(h, s) {
    var d = h.detail;
    var models = clear(d.modelsBox);
    var list = el("ul", "mon-list");
    (s.models || []).forEach(function (m) {
      var li = el("li");
      if (m.auth) {
        li.textContent = "Models behind an API key, served by " + m.container + (m.port ? " (port " + m.port + ")" : "");
      } else {
        var extra = [];
        extra.push("in " + m.container);
        if (m.port) extra.push("port " + m.port);
        if (num(m.max_len)) extra.push(Math.round(m.max_len / 1024) + "k context");
        li.appendChild(el("strong", null, m.id));
        li.appendChild(document.createTextNode(", " + extra.join(", ")));
      }
      list.appendChild(li);
    });
    if (list.children.length) models.appendChild(list);
    else models.appendChild(el("p", "mon-note", "No models found on this server."));

    var routes = clear(d.routesBox);
    var rl = el("ul", "mon-list");
    (s.routes || []).forEach(function (r) {
      var li = el("li");
      var a = el("a", null, r.url.replace(/^https?:\/\//, ""));
      a.href = r.url;
      a.rel = "noopener";
      li.appendChild(a);
      if (r.container) li.appendChild(el("span", "mon-muted", ", " + r.container));
      rl.appendChild(li);
    });
    if (rl.children.length) routes.appendChild(rl);
    else routes.appendChild(el("p", "mon-note", "No web services found in this server's proxy configuration."));

    var cont = clear(d.containersBox);
    var items = s.containers || [];
    if (!items.length) {
      cont.appendChild(el("p", "mon-note", s.containers_status === "ok" ? "No containers." : "Container list unavailable."));
      return;
    }
    var t = table(["Container", "Image", "State", "GPUs"]);
    items.forEach(function (c) {
      var tr = el("tr", c.state === "running" ? null : "mon-stopped");
      var name = el("td", null, c.name);
      if (c.project && c.project !== c.name) name.appendChild(el("span", "mon-proc mon-muted", c.project));
      tr.appendChild(name);
      tr.appendChild(td(c.image || "n/a"));
      tr.appendChild(td((c.state || "unknown") + (c.health ? ", " + c.health : "")));
      tr.appendChild(td(c.gpus && c.gpus.length ? c.gpus.join(", ") + (num(c.gpu_mem_gib) && c.gpu_mem_gib > 0 ? " (" + gib(c.gpu_mem_gib) + ")" : "") : ""));
      t.body.appendChild(tr);
    });
    cont.appendChild(t.wrap);
  }

  function renderStorage(h) {
    var box = clear(h.detail.storageBox);
    var mounts = (h.now && h.now.mounts) || {};
    var keys = Object.keys(mounts);
    if (!keys.length) {
      box.appendChild(el("p", "mon-note", "No filesystems reported."));
      return;
    }
    var t = table(["Filesystem", "Used", "Size"]);
    keys.forEach(function (k) {
      var m = mounts[k];
      var tr = el("tr");
      tr.appendChild(td(m.path || k));
      var used = el("td");
      used.appendChild(el("span", "mon-value", pct(m.used_pct)));
      var meter = el("span", "mon-meter");
      var fill = el("i");
      fill.style.width = num(m.used_pct) ? m.used_pct + "%" : "0";
      meter.appendChild(fill);
      used.appendChild(meter);
      tr.appendChild(used);
      tr.appendChild(td(pair(m.used_gib, m.total_gib, "GiB")));
      t.body.appendChild(tr);
    });
    box.appendChild(t.wrap);
  }

  function every(h, seconds, fn) {
    fn();
    h.detail.timers.push(setInterval(function () {
      if (!hidden) fn();
    }, seconds * 1000));
  }

  function openDetail(h) {
    if (!h.detail) buildDetail(h);
    var d = h.detail;
    d.open = true;
    h.detailEl.hidden = false;
    h.button.setAttribute("aria-expanded", "true");
    every(h, 600, function () {
      getJSON(h, "host.json").then(function (res) {
        h.host = res.json;
        renderFacts(h, res.json);
      }).catch(function () {
        d.facts.textContent = "Server details unavailable.";
      });
    });
    every(h, 10, function () {
      loadHistory(h);
    });
    every(h, 10, function () {
      getJSON(h, "procs.json").then(function (res) {
        renderGpus(h, res.json);
      }).catch(function () {
        renderGpus(h, null);
      });
      renderStorage(h);
    });
    every(h, 60, function () {
      getJSON(h, "services.json").then(function (res) {
        renderServices(h, res.json);
      }).catch(function () {
        clear(d.modelsBox).appendChild(el("p", "mon-note", "Services unavailable."));
      });
    });
    renderDailyChart(h);
  }

  function closeDetail(h) {
    var d = h.detail;
    if (!d) return;
    d.open = false;
    d.timers.forEach(clearInterval);
    d.timers = [];
    h.detailEl.hidden = true;
    h.button.setAttribute("aria-expanded", "false");
  }

  // visibility --------------------------------------------------------------------

  function pauseAll() {
    hidden = true;
    clearTimeout(overviewTimer);
    if (overviewCtl) overviewCtl.abort();
  }

  function resumeAll() {
    hidden = false;
    scheduleOverview(0);
  }

  // init --------------------------------------------------------------------------

  function init() {
    var node = document.getElementById("monitor-config");
    if (!node) return;
    cfg = JSON.parse(node.textContent);
    base = dataBase();

    if (window.Chart) {
      window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    }

    resumeAll();

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        pauseAll();
      } else {
        resumeAll();
      }
    });

    new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
