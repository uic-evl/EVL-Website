// /history/ ("50+ Years"): scroll steps, the sticky panel, the timeline guide and the
// Part 06 charts. Content comes from the page (_includes/history/*.liquid); without this
// script the page reads as a plain article.
(function () {
  "use strict";

  var root = document.querySelector(".evl-history");
  if (!root) return;

  var html = document.documentElement;
  var wide = window.matchMedia("(min-width: 992px)");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var SVG_NS = "http://www.w3.org/2000/svg";

  // Lane order, top to bottom (the legend follows AREAS too).
  // label: lane label; tiny: lane label on phones; short: name in tooltips and the legend.
  var AREAS = [
    { key: "vis", label: "VIS · visual computing", tiny: "VIS", short: "Visualization" },
    { key: "art", label: "Art · art & design", tiny: "Art", short: "Art & design" },
    { key: "hci", label: "HCI · people & interaction", tiny: "HCI", short: "HCI" },
    { key: "hpc", label: "HPC · systems & networks", tiny: "HPC", short: "HPC" }
  ];
  var DOMAINS = [
    { key: "platforms", label: "Instruments & platforms", tiny: "Instruments" },
    { key: "arts", label: "Arts & culture", tiny: "Arts" },
    { key: "science", label: "Science & engineering", tiny: "Science" },
    { key: "biomed", label: "Biomedicine & health", tiny: "Biomedicine" },
    { key: "earth", label: "Earth & environment", tiny: "Earth" },
    { key: "cities", label: "Cities", tiny: "Cities" },
    { key: "learning", label: "Learning", tiny: "Learning" }
  ];

  function toArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function readJSON(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (e) {
      return null;
    }
    return null;
  }

  function scrollBehavior() {
    return reduceMotion.matches ? "auto" : "smooth";
  }

  function cssVar(name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  }

  function svgEl(tag, attrs, parent) {
    var el = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) el.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(el);
    return el;
  }

  function formatNumber(n) {
    return Number(n).toLocaleString("en-US");
  }

  function shortNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 10000) return Math.round(n / 1000) + "k";
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return String(n);
  }

  // -------------------------------------------------------------------------------------
  // Steps, the sticky panel and collapsed groups

  var steps = toArray(root.querySelectorAll(".history-step"));
  var activeStep = null;
  var lastYear = null;
  var listeners = [];

  function isShown(el) {
    return el.offsetParent !== null;
  }

  function stepYear(step) {
    var y = parseInt(step.getAttribute("data-year"), 10);
    return isNaN(y) ? null : y;
  }

  function showFrame(step) {
    var chapter = step.closest(".history-chapter");
    if (!chapter) return;
    var frames = toArray(chapter.querySelectorAll(".history-panel-frame"));
    if (!frames.length) return;
    var target = null;
    var chapterSteps = toArray(chapter.querySelectorAll(".history-step"));
    var idx = chapterSteps.indexOf(step);
    for (var i = idx; i >= 0 && !target; i--) {
      if (i !== idx && !isShown(chapterSteps[i])) continue;
      var id = chapterSteps[i].id;
      for (var j = 0; j < frames.length; j++) {
        if (frames[j].getAttribute("data-frame") === id) {
          target = frames[j];
          break;
        }
      }
    }
    if (!target) target = frames[0];
    frames.forEach(function (f) {
      var on = f === target;
      f.classList.toggle("is-shown", on);
      if (on) f.removeAttribute("aria-hidden");
      else f.setAttribute("aria-hidden", "true");
    });
    if (target) drawChartsIn(target);
  }

  function update() {
    var focus = window.innerHeight * 0.45;
    var shown = steps.filter(isShown);
    var current = null;
    var progress = 0;
    for (var i = 0; i < shown.length; i++) {
      var rect = shown[i].getBoundingClientRect();
      if (rect.top <= focus) {
        current = shown[i];
        progress = rect.height ? Math.min(1, Math.max(0, (focus - rect.top) / rect.height)) : 0;
      } else {
        break;
      }
    }
    // The chapter under the reading line (its opener counts too).
    var chapter = null;
    toArray(root.querySelectorAll(".history-chapter")).some(function (ch) {
      var r = ch.getBoundingClientRect();
      if (r.top <= focus && r.bottom > focus) {
        chapter = ch;
        return true;
      }
      return false;
    });
    if (current && (current.getBoundingClientRect().bottom < 0 || chapterOf(current) !== chapter)) current = null;

    if (current !== activeStep) {
      if (activeStep) activeStep.classList.remove("is-active");
      activeStep = current;
      if (activeStep) {
        activeStep.classList.add("is-active");
        if (wide.matches) showFrame(activeStep);
      }
    }

    // The year the timeline playhead points at: the active step's, gliding toward the next.
    var year = null;
    if (current) {
      year = stepYear(current);
      if (year === null) {
        year = lastYear;
      } else {
        var idx = shown.indexOf(current);
        for (var k = idx + 1; k < shown.length; k++) {
          var next = stepYear(shown[k]);
          if (next !== null) {
            if (next > year && next - year <= 12) year = year + (next - year) * progress;
            break;
          }
        }
        lastYear = stepYear(current);
      }
    }
    listeners.forEach(function (fn) {
      fn(current, year, chapter);
    });
  }

  var ticking = false;
  function requestUpdate() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      update();
    });
  }

  function chapterOf(el) {
    return el ? el.closest(".history-chapter") : null;
  }

  function openCard(step) {
    step.classList.add("is-open");
    var chapter = chapterOf(step);
    if (!chapter) return;
    var scrolly = chapter.querySelector(".history-scrolly");
    if (scrolly) scrolly.classList.add("has-open");
    toArray(chapter.querySelectorAll('.history-card[data-open="' + step.id + '"]')).forEach(function (c) {
      c.classList.add("is-open");
    });
  }

  // Make a step visible (opening its card) and scroll it into view.
  function reveal(step, behavior) {
    if (!step) return;
    if (step.classList.contains("history-step--card")) openCard(step);
    window.requestAnimationFrame(function () {
      step.scrollIntoView({ behavior: behavior || scrollBehavior(), block: "start" });
      requestUpdate();
    });
  }

  toArray(root.querySelectorAll(".history-card")).forEach(function (card) {
    card.addEventListener("click", function (event) {
      var step = document.getElementById(card.getAttribute("data-open"));
      if (!step) return;
      event.preventDefault();
      reveal(step);
      if (window.history && window.history.replaceState) window.history.replaceState(null, "", "#" + step.id);
    });
  });

  function revealHash() {
    var id = decodeURIComponent((window.location.hash || "").slice(1));
    if (!id) return;
    var target = document.getElementById(id);
    if (target && target.classList.contains("history-step") && !isShown(target)) reveal(target, "auto");
  }

  // -------------------------------------------------------------------------------------
  // Timeline guide

  var guide = document.getElementById("history-guide");
  var marksData = readJSON("history-marks");

  function setupGuide() {
    if (!guide || !marksData) return;
    var plot = guide.querySelector(".history-guide-plot");
    var eraEl = guide.querySelector(".history-guide-era");
    var stepEl = guide.querySelector(".history-guide-step");
    var collapseBtn = guide.querySelector(".history-guide-collapse");
    var toggleBtns = toArray(guide.querySelectorAll(".history-guide-toggle button"));
    var from = Math.floor(marksData.from / 10) * 10;
    var to = marksData.to;
    var decades = [];
    for (var d = from; d <= Math.floor(to / 10) * 10; d += 10) decades.push(d);
    var span = decades.length * 10;
    var marks = marksData.marks.filter(function (m) {
      return m.year >= marksData.from && m.year <= to;
    });
    var eras = {};
    (marksData.eras || []).forEach(function (e) {
      eras[e.part] = e;
    });

    var state = {
      group: store("evl-history-timeline-group") === "area" ? "area" : "domain",
      year: null,
      activeId: null
    };

    var chart = document.createElement("div");
    chart.className = "history-guide-chart";
    var labels = document.createElement("div");
    labels.className = "history-guide-labels";
    var track = document.createElement("div");
    track.className = "history-guide-track";
    chart.appendChild(labels);
    chart.appendChild(track);
    var axis = document.createElement("div");
    axis.className = "history-guide-axis";
    var legend = document.createElement("div");
    legend.className = "history-guide-legend";
    var tip = document.createElement("div");
    tip.className = "history-guide-tip";
    tip.hidden = true;
    var playhead = document.createElement("div");
    playhead.className = "history-guide-playhead";
    playhead.setAttribute("aria-hidden", "true");
    plot.appendChild(chart);
    plot.appendChild(axis);
    plot.appendChild(legend);
    plot.appendChild(tip);

    var markEls = [];
    var decadeBtns = [];

    function lanes() {
      return state.group === "domain" ? DOMAINS : AREAS;
    }

    function laneHeight() {
      var small = window.innerWidth < 768;
      if (state.group === "domain") return small ? 10 : 13;
      return small ? 12 : 16;
    }

    function decadeOf(year) {
      return Math.floor(year / 10) * 10;
    }

    function build() {
      labels.innerHTML = "";
      track.innerHTML = "";
      markEls = [];
      decadeBtns = [];
      var h = laneHeight();
      lanes().forEach(function (lane) {
        var label = document.createElement("div");
        label.className = "history-guide-label";
        label.style.height = h + "px";
        if (state.group === "area") {
          var sw = document.createElement("span");
          sw.className = "history-guide-swatch";
          sw.style.background = "var(--history-" + lane.key + ")";
          label.appendChild(sw);
        }
        var labelText = document.createElement("span");
        labelText.className = "history-guide-label-text";
        labelText.textContent = window.innerWidth < 768 ? lane.tiny : lane.label;
        label.appendChild(labelText);
        label.title = lane.label;
        labels.appendChild(label);

        var row = document.createElement("div");
        row.className = "history-guide-lane";
        row.style.height = h + "px";
        track.appendChild(row);

        marks.forEach(function (m) {
          if ((state.group === "domain" ? m.domain : m.area) !== lane.key) return;
          // Every dot is something the story tells; a click picks the decade behind it.
          var el = document.createElement("span");
          el.className = "history-guide-mark";
          el.setAttribute("aria-hidden", "true");
          el.style.setProperty("--mark-color", "var(--history-" + m.area + ")");
          row.appendChild(el);
          markEls.push({ el: el, m: m, lane: lane.key });
        });
      });

      var firstLane = track.firstChild;
      decades.forEach(function (dec, i) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "history-guide-decade";
        btn.style.left = (i * 10 * 100) / span + "%";
        btn.style.width = (10 * 100) / span + "%";
        var count = marks.filter(function (m) {
          return decadeOf(m.year) === dec;
        }).length;
        var counted = count + (count === 1 ? " milestone" : " milestones");
        btn.setAttribute("aria-label", "Jump to the " + dec + "s (" + counted + ")");
        btn.addEventListener("click", function () {
          jumpTo(dec);
        });
        btn.addEventListener("mouseenter", function () {
          showTip(btn, dec + "s", counted + " · select to jump there");
        });
        btn.addEventListener("focus", function () {
          showTip(btn, dec + "s", counted + " · select to jump there");
        });
        btn.addEventListener("mouseleave", hideTip);
        btn.addEventListener("blur", hideTip);
        // Behind the lanes, in decade order (keyboard order too).
        track.insertBefore(btn, firstLane);
        decadeBtns.push({ el: btn, decade: dec });
      });
      track.appendChild(playhead);

      legend.innerHTML = "";
      if (state.group === "domain") {
        AREAS.forEach(function (a) {
          var item = document.createElement("span");
          var sw = document.createElement("i");
          sw.className = "history-guide-swatch";
          sw.style.background = "var(--history-" + a.key + ")";
          item.appendChild(sw);
          item.appendChild(document.createTextNode(a.short));
          legend.appendChild(item);
        });
      }
      if (window.innerWidth >= 768) {
        var hint = document.createElement("span");
        hint.className = "history-guide-hint";
        hint.textContent = "Select a decade to jump to it";
        legend.appendChild(hint);
      }
      toggleBtns.forEach(function (b) {
        b.setAttribute("aria-checked", b.getAttribute("data-group") === state.group ? "true" : "false");
      });
      layout();
    }

    // Each decade's milestones, packed into one cluster per lane at the decade's centre.
    function layout() {
      var width = track.clientWidth || 1;
      var colWidth = (width * 10) / span;
      var groups = {};
      markEls.forEach(function (item) {
        var key = item.lane + "|" + decadeOf(item.m.year);
        (groups[key] = groups[key] || []).push(item);
      });
      Object.keys(groups).forEach(function (key) {
        var list = groups[key].sort(function (a, b) {
          return a.m.year - b.m.year || (a.m.primary ? -1 : 1);
        });
        var n = list.length;
        var gap = Math.min(10, n > 1 ? (colWidth - 14) / (n - 1) : 10);
        list.forEach(function (item, i) {
          var dIndex = decades.indexOf(decadeOf(item.m.year));
          item.el.style.left = (dIndex + 0.5) * colWidth + (i - (n - 1) / 2) * gap + "px";
        });
      });

      axis.innerHTML = "";
      decades.forEach(function (dec, i) {
        var t = document.createElement("span");
        t.className = "history-guide-tick";
        t.style.left = ((i + 0.5) * 100 * 10) / span + "%";
        t.textContent = dec + "s";
        axis.appendChild(t);
      });
      placePlayhead();
      setActiveMark();
    }

    // The last year a part claims ("1990–1999" ends in 1999; "Today" and "1973–today" never end).
    function partEnd(step) {
      var chapter = step.closest(".history-chapter");
      var years = ((chapter && chapter.getAttribute("data-years")) || "").match(/\d{4}/g);
      return years && years.length > 1 ? parseInt(years[1], 10) : Infinity;
    }

    // Jump to the earliest step the story tells in a decade (the first one read, when years tie),
    // opening its card if it is closed. A part that ends before the decade doesn't count:
    // StarLight (2001) closes the 1990s.
    function jumpTo(dec) {
      var target = null;
      steps.forEach(function (s) {
        var y = stepYear(s);
        if (y === null || decadeOf(y) !== dec || partEnd(s) < dec) return;
        if (!target || y < stepYear(target)) target = s;
      });
      hideTip();
      reveal(target);
    }

    function placePlayhead() {
      var y = state.year;
      var none = y === null || y === undefined;
      playhead.style.display = none ? "none" : "";
      if (!none) playhead.style.left = ((y - from + 0.5) / span) * 100 + "%";
      decadeBtns.forEach(function (b) {
        b.el.classList.toggle("is-current", !none && b.decade === decadeOf(Math.round(y)));
      });
    }

    // The active step's own dot stands out; the other dates it tells about get a ring.
    function setActiveMark() {
      markEls.forEach(function (item) {
        var mine = item.m.id === state.activeId;
        item.el.classList.toggle("is-active", mine && item.m.primary);
        item.el.classList.toggle("is-related", mine && !item.m.primary);
      });
    }

    function showTip(el, title, text) {
      tip.innerHTML = "";
      var strong = document.createElement("strong");
      strong.textContent = title;
      var meta = document.createElement("span");
      meta.textContent = text;
      tip.appendChild(strong);
      tip.appendChild(meta);
      tip.hidden = false;
      var p = plot.getBoundingClientRect();
      var r = el.getBoundingClientRect();
      var left = r.left - p.left + r.width / 2 - tip.offsetWidth / 2;
      left = Math.max(0, Math.min(left, p.width - tip.offsetWidth));
      tip.style.left = left + "px";
      // Under the axis and the legend, clear of the dots.
      tip.style.top = p.height + 6 + "px";
    }

    function hideTip() {
      tip.hidden = true;
    }

    toggleBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        state.group = b.getAttribute("data-group");
        store("evl-history-timeline-group", state.group);
        build();
      });
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          var other = toggleBtns[toggleBtns.indexOf(b) === 0 ? 1 : 0];
          other.click();
          other.focus();
        }
      });
    });

    function setCollapsed(collapsed) {
      guide.classList.toggle("is-collapsed", collapsed);
      collapseBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      collapseBtn.querySelector(".history-guide-collapse-label").textContent = collapsed ? "Show timeline" : "Hide timeline";
      if (!collapsed) layout();
    }

    collapseBtn.addEventListener("click", function () {
      var collapsed = !guide.classList.contains("is-collapsed");
      store("evl-history-timeline-hidden", collapsed ? "1" : "0");
      setCollapsed(collapsed);
    });

    // Open by default on every screen; a reader who hides it keeps it hidden.
    setCollapsed(store("evl-history-timeline-hidden") === "1");

    // Publish the offsets below the navbar and the guide, so sticky panels and anchors sit
    // under them. They go out as plain pixels: the site's CSS minifier garbles var() in calc().
    function publishHeight() {
      var top = (parseFloat(window.getComputedStyle(root).getPropertyValue("--history-navbar")) || 68) + guide.offsetHeight + 16;
      root.style.setProperty("--history-top", top + "px");
      root.style.setProperty("--history-panel-h", Math.max(240, window.innerHeight - top - 16) + "px");
      root.style.setProperty("--history-panel-img-h", Math.max(180, window.innerHeight - top - 80) + "px");
    }
    window.addEventListener("resize", publishHeight);
    // Lane labels and heights depend on the phone breakpoint: rebuild when it is crossed.
    var builtSmall = window.innerWidth < 768;
    function onGuideResize() {
      var small = window.innerWidth < 768;
      if (small !== builtSmall) {
        builtSmall = small;
        build();
      } else {
        layout();
      }
      publishHeight();
    }
    if (window.ResizeObserver) {
      new ResizeObserver(onGuideResize).observe(guide);
    } else {
      window.addEventListener("resize", onGuideResize);
    }
    publishHeight();

    build();

    listeners.push(function (step, year, chapter) {
      if (chapter) {
        var part = chapter.getAttribute("data-part");
        eraEl.textContent = "Part " + part + " · " + chapter.getAttribute("data-years") + " · " + chapter.getAttribute("data-title");
        var title = step ? step.querySelector(".history-step-title") : null;
        stepEl.textContent = title ? title.textContent : "";
      } else {
        eraEl.textContent = "1973 → " + to;
        stepEl.textContent = "";
      }
      state.activeId = step ? step.id : null;
      state.year = year === null || year === undefined ? null : year;
      placePlayhead();
      setActiveMark();
    });
  }

  // -------------------------------------------------------------------------------------
  // Part 06 charts (lab-level aggregates only)

  var data = readJSON("history-data") || {};

  function colors() {
    return {
      hpc: cssVar("--history-hpc") || "#2a78d6",
      vis: cssVar("--history-vis") || "#c1440e",
      hci: cssVar("--history-hci") || "#d4a017",
      art: cssVar("--history-art") || "#b0479a",
      ink: cssVar("--history-ink") || "#1b1b1f",
      muted: cssVar("--history-muted") || "#5c5c66",
      rule: cssVar("--history-rule") || "rgba(0,0,0,.08)",
      surface: cssVar("--history-surface") || "#fff"
    };
  }

  function text(parent, x, y, content, attrs) {
    var t = svgEl("text", attrs || {}, parent);
    t.setAttribute("x", x);
    t.setAttribute("y", y);
    t.textContent = content;
    return t;
  }

  var CHARTS = {
    software: function (svg, c) {
      var sw = data.software;
      if (!sw || !sw.downloads) {
        svg.setAttribute("viewBox", "0 0 600 60");
        text(svg, 0, 30, "Download figures were not available when the site was built.", { "font-size": 13, class: "history-chart-muted" });
        return;
      }
      var rows = [];
      sw.years.forEach(function (y, i) {
        var v = sw.downloads[i];
        if (v !== null && v !== undefined) rows.push({ year: y, value: v, current: sw.current && i === sw.years.length - 1 });
      });
      while (rows.length && rows[0].value === 0) rows.shift();
      if (!rows.length) return;
      var W = 600;
      var H = 300;
      var top = 34;
      var bottom = 250;
      var max = Math.max.apply(null, rows.map(function (r) { return r.value; })) || 1;
      var step = 10;
      while (max / step > 5) step *= max / step > 25 ? 5 : 2;
      var nice = Math.ceil(max / step) * step;
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      for (var g = 0; g <= nice; g += step) {
        var gy = bottom - (g / nice) * (bottom - top);
        svgEl("line", { x1: 44, x2: W, y1: gy, y2: gy, class: "history-chart-rule", "stroke-width": 1 }, svg);
        text(svg, 38, gy + 4, shortNumber(g), { "font-size": 11, "text-anchor": "end", class: "history-chart-muted" });
      }
      var band = (W - 60) / rows.length;
      var bw = Math.min(64, band * 0.6);
      rows.forEach(function (r, i) {
        var x = 60 + i * band + (band - bw) / 2;
        var h = (r.value / nice) * (bottom - top);
        var bar = svgEl("rect", {
          x: x,
          y: bottom - h,
          width: bw,
          height: Math.max(1, h),
          rx: 4,
          fill: c.hpc,
          "fill-opacity": r.current ? 0.55 : 1
        }, svg);
        svgEl("title", {}, bar).textContent = r.year + (r.current ? " (so far)" : "") + ": " + formatNumber(r.value) + " downloads";
        text(svg, x + bw / 2, bottom - h - 8, shortNumber(r.value), { "font-size": 12, "font-weight": 600, "text-anchor": "middle" });
        text(svg, x + bw / 2, bottom + 18, r.year, { "font-size": 12, "text-anchor": "middle", class: "history-chart-muted" });
        if (r.current) text(svg, x + bw / 2, bottom + 33, "so far", { "font-size": 10.5, "text-anchor": "middle", class: "history-chart-muted" });
      });
      text(svg, 0, 16, "Package downloads per year", { "font-size": 12, class: "history-chart-muted" });
    }
  };

  function drawChart(mount) {
    var id = mount.getAttribute("data-chart");
    if (!CHARTS[id] || !isShown(mount)) return;
    mount.innerHTML = "";
    var svg = svgEl("svg", { preserveAspectRatio: "xMidYMid meet", "aria-hidden": "true", focusable: "false" }, mount);
    CHARTS[id](svg, colors());
    mount.setAttribute("data-drawn", "1");
  }

  function drawChartsIn(scope) {
    toArray(scope.querySelectorAll(".history-chart")).forEach(drawChart);
  }

  function redrawCharts() {
    toArray(root.querySelectorAll('.history-chart[data-drawn="1"]')).forEach(drawChart);
  }

  function setupCharts() {
    var mounts = toArray(root.querySelectorAll(".history-chart"));
    if (!mounts.length) return;
    if (window.IntersectionObserver) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting && !entry.target.getAttribute("data-drawn")) drawChart(entry.target);
          });
        },
        { rootMargin: "200px 0px" }
      );
      mounts.forEach(function (m) {
        io.observe(m);
      });
    } else {
      mounts.forEach(drawChart);
    }
    // Re-colour when the reader switches between light and dark.
    new MutationObserver(redrawCharts).observe(html, { attributes: true, attributeFilter: ["data-theme"] });
  }

  // -------------------------------------------------------------------------------------

  setupGuide();
  setupCharts();
  revealHash();
  window.addEventListener("hashchange", revealHash);
  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  var onWide = function () {
    if (wide.matches && activeStep) showFrame(activeStep);
    redrawCharts();
    requestUpdate();
  };
  if (wide.addEventListener) wide.addEventListener("change", onWide);
  else if (wide.addListener) wide.addListener(onWide);
  update();
})();
