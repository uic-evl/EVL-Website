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

  function setMoreOpen(chapter, open) {
    var toggle = chapter.querySelector(".history-more-toggle");
    toArray(chapter.querySelectorAll(".history-step--more")).forEach(function (s) {
      s.classList.toggle("is-open", open);
    });
    if (toggle) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      var label = toggle.querySelector(".history-more-label");
      if (label) {
        if (!label.getAttribute("data-label-closed")) label.setAttribute("data-label-closed", label.textContent);
        label.textContent = open ? label.getAttribute("data-label-open") : label.getAttribute("data-label-closed");
      }
    }
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

  // Make a step visible (opening its group or card) and scroll it into view.
  function reveal(step, behavior) {
    if (!step) return;
    if (step.classList.contains("history-step--more") && !step.classList.contains("is-open")) {
      setMoreOpen(chapterOf(step), true);
    }
    if (step.classList.contains("history-step--card")) openCard(step);
    window.requestAnimationFrame(function () {
      step.scrollIntoView({ behavior: behavior || scrollBehavior(), block: "start" });
      requestUpdate();
    });
  }

  toArray(root.querySelectorAll(".history-more-toggle")).forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      var chapter = chapterOf(toggle);
      var open = toggle.getAttribute("aria-expanded") !== "true";
      setMoreOpen(chapter, open);
      if (open) {
        var first = chapter.querySelector(".history-step--more");
        if (first) reveal(first);
      } else {
        toggle.scrollIntoView({ behavior: "auto", block: "center" });
      }
      requestUpdate();
    });
  });

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
      zoom: null, // a decade, or null for the overview
      year: null,
      activeId: null,
      heldUntil: 0, // after the reader picks a decade, don't follow the scroll for a moment
      hovered: false
    };
    guide.addEventListener("mouseenter", function () {
      state.hovered = true;
    });
    guide.addEventListener("mouseleave", function () {
      state.hovered = false;
    });

    var crumb = document.createElement("div");
    crumb.className = "history-guide-crumb";
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
    plot.appendChild(crumb);
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

    function areaName(key) {
      for (var i = 0; i < AREAS.length; i++) if (AREAS[i].key === key) return AREAS[i].short;
      return key;
    }

    function domainName(key) {
      for (var i = 0; i < DOMAINS.length; i++) if (DOMAINS[i].key === key) return DOMAINS[i].label;
      return key;
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
          // Every dot is something the story tells; it opens the step that tells it.
          var el = document.createElement("button");
          el.type = "button";
          el.className = "history-guide-mark";
          el.style.setProperty("--mark-color", "var(--history-" + m.area + ")");
          el.setAttribute("aria-label", (m.label || m.year) + ", " + m.title + " (" + areaName(m.area) + ", " + domainName(m.domain) + ")");
          el.addEventListener("mouseenter", function () {
            showTip(el, m);
          });
          el.addEventListener("focus", function () {
            showTip(el, m);
          });
          el.addEventListener("mouseleave", hideTip);
          el.addEventListener("blur", hideTip);
          el.addEventListener("click", function () {
            reveal(document.getElementById(m.id));
          });
          el.addEventListener("keydown", function (e) {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
            var siblings = toArray(row.querySelectorAll(".history-guide-mark")).filter(function (s) {
              return s.style.display !== "none";
            });
            siblings.sort(function (a, b) {
              return parseFloat(a.getAttribute("data-x")) - parseFloat(b.getAttribute("data-x"));
            });
            var i = siblings.indexOf(el) + (e.key === "ArrowRight" ? 1 : -1);
            if (siblings[i]) {
              e.preventDefault();
              siblings[i].focus();
            }
          });
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
        btn.setAttribute("aria-label", "Zoom into the " + dec + "s (" + count + " milestones)");
        btn.addEventListener("click", function () {
          zoomTo(dec);
        });
        var decadeTip = { title: dec + "s", year: count + (count === 1 ? " milestone" : " milestones"), decade: true };
        btn.addEventListener("mouseenter", function () {
          showTip(btn, decadeTip);
        });
        btn.addEventListener("focus", function () {
          showTip(btn, decadeTip);
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
      toggleBtns.forEach(function (b) {
        b.setAttribute("aria-checked", b.getAttribute("data-group") === state.group ? "true" : "false");
      });
      layout();
    }

    function layout() {
      var width = track.clientWidth || 1;
      var colWidth = (width * 10) / span;
      var groups = {};
      markEls.forEach(function (item) {
        var m = item.m;
        var key = state.zoom === null ? item.lane + "|" + decadeOf(m.year) : item.lane + "|" + m.year;
        (groups[key] = groups[key] || []).push(item);
      });
      Object.keys(groups).forEach(function (key) {
        var list = groups[key].sort(function (a, b) {
          return a.m.year - b.m.year || (a.m.primary ? -1 : 1);
        });
        var n = list.length;
        list.forEach(function (item, i) {
          var m = item.m;
          var el = item.el;
          var x;
          if (state.zoom === null) {
            // Overview: each decade's milestones packed into a cluster at the decade's centre.
            // The decade itself is the click target here; single dots open once zoomed in.
            var dIndex = decades.indexOf(decadeOf(m.year));
            var gap = Math.min(10, n > 1 ? (colWidth - 14) / (n - 1) : 10);
            x = (dIndex + 0.5) * colWidth + (i - (n - 1) / 2) * gap;
            el.style.display = "";
            el.style.pointerEvents = "none";
            el.tabIndex = -1;
          } else if (decadeOf(m.year) === state.zoom) {
            // Zoomed: spread to their own years.
            x = ((m.year - state.zoom + 0.5) / 10) * width + (i - (n - 1) / 2) * 9;
            el.style.display = "";
            el.style.pointerEvents = "";
            el.removeAttribute("tabindex");
          } else {
            el.style.display = "none";
            return;
          }
          el.style.left = x + "px";
          el.setAttribute("data-x", x);
        });
      });

      decadeBtns.forEach(function (b) {
        b.el.style.display = state.zoom === null ? "" : "none";
      });

      axis.innerHTML = "";
      if (state.zoom === null) {
        decades.forEach(function (dec, i) {
          var t = document.createElement("span");
          t.className = "history-guide-tick";
          t.style.left = ((i + 0.5) * 100 * 10) / span + "%";
          t.textContent = dec + "s";
          axis.appendChild(t);
        });
      } else {
        for (var y = state.zoom; y < state.zoom + 10; y++) {
          var tick = document.createElement("span");
          tick.className = "history-guide-tick";
          tick.style.left = ((y - state.zoom + 0.5) / 10) * 100 + "%";
          tick.textContent = y > to ? "" : y;
          axis.appendChild(tick);
        }
      }
      renderCrumb();
      placePlayhead();
      setActiveMark();
    }

    function renderCrumb() {
      crumb.innerHTML = "";
      if (state.zoom === null) {
        var hint = document.createElement("span");
        hint.textContent = window.innerWidth < 768 ? "Tap a decade to zoom in" : "All decades · select a decade to see its milestones";
        crumb.appendChild(hint);
        return;
      }
      var i = decades.indexOf(state.zoom);
      function btn(text, fn, label) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = text;
        if (label) b.setAttribute("aria-label", label);
        b.addEventListener("click", fn);
        crumb.appendChild(b);
      }
      btn("All decades", function () {
        zoomTo(null);
      });
      crumb.appendChild(document.createTextNode("›"));
      if (decades[i - 1] !== undefined) {
        btn("‹ " + decades[i - 1] + "s", function () {
          zoomTo(decades[i - 1]);
        }, "Previous decade");
      }
      var strong = document.createElement("strong");
      strong.textContent = state.zoom + "s";
      crumb.appendChild(strong);
      if (decades[i + 1] !== undefined) {
        btn(decades[i + 1] + "s ›", function () {
          zoomTo(decades[i + 1]);
        }, "Next decade");
      }
    }

    function zoomTo(dec) {
      state.zoom = dec;
      state.heldUntil = Date.now() + 4000;
      hideTip();
      layout();
    }

    function placePlayhead() {
      var y = state.year;
      if (y === null || y === undefined) {
        playhead.style.display = "none";
        return;
      }
      var pct;
      if (state.zoom === null) {
        pct = ((y - from + 0.5) / span) * 100;
      } else if (y >= state.zoom && y < state.zoom + 10) {
        pct = ((y - state.zoom + 0.5) / 10) * 100;
      } else {
        playhead.style.display = "none";
        return;
      }
      playhead.style.display = "";
      playhead.style.left = pct + "%";
      decadeBtns.forEach(function (b) {
        b.el.classList.toggle("is-current", b.decade === decadeOf(Math.round(y)));
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

    function showTip(el, m) {
      tip.innerHTML = "";
      var strong = document.createElement("strong");
      strong.textContent = m.title;
      var meta = document.createElement("span");
      meta.textContent = m.decade ? m.year + " · select to zoom in" : (m.label || m.year) + " · " + areaName(m.area) + " · " + domainName(m.domain);
      tip.appendChild(strong);
      tip.appendChild(meta);
      tip.hidden = false;
      var p = plot.getBoundingClientRect();
      var r = el.getBoundingClientRect();
      var left = r.left - p.left + r.width / 2 - tip.offsetWidth / 2;
      left = Math.max(0, Math.min(left, p.width - tip.offsetWidth));
      tip.style.left = left + "px";
      // Decade tips sit under the axis; dot tips sit just under the dot.
      tip.style.top = (m.decade ? p.height : r.bottom - p.top) + 6 + "px";
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
      // Follow the reader into another decade, unless they just picked one or are using the guide.
      if (state.zoom !== null && state.year !== null && !state.hovered && Date.now() > state.heldUntil) {
        var dec = decadeOf(Math.round(state.year));
        if (dec !== state.zoom) {
          state.zoom = dec;
          layout();
          return;
        }
      }
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
    mix: function (svg, c) {
      var pub = data.publications;
      if (!pub) return;
      var W = 600;
      var total = pub.records;
      var parts = [
        { key: "hpc", label: "HPC", sub: "systems & scale", value: pub.mix.hpc },
        { key: "vis", label: "Visualization", sub: "visual computing", value: pub.mix.vis },
        { key: "hci", label: "HCI", sub: "people & interaction", value: pub.mix.hci }
      ];
      svg.setAttribute("viewBox", "0 0 " + W + " 190");
      var x = 0;
      parts.forEach(function (p, i) {
        var w = (p.value / total) * W;
        var gap = i < parts.length - 1 ? 2 : 0;
        var rect = svgEl("rect", { x: x, y: 74, width: Math.max(0, w - gap), height: 40, rx: 4, fill: c[p.key] }, svg);
        svgEl("title", {}, rect).textContent = p.label + ": " + Math.round((p.value / total) * 100) + "% of " + formatNumber(total) + " weighted records";
        text(svg, x, 40, Math.round((p.value / total) * 100) + "%", { "font-size": 26, "font-weight": 700 });
        text(svg, x, 62, p.label + " · " + p.sub, { "font-size": 12, class: "history-chart-muted" });
        x += w;
      });
      text(svg, 0, 150, formatNumber(total) + " weighted career records · " + pub.people + " faculty and affiliated faculty", {
        "font-size": 12,
        class: "history-chart-muted"
      });
      text(svg, 0, 172, "A record that spans two areas splits evenly", { "font-size": 12, class: "history-chart-muted" });
    },

    territory: function (svg, c) {
      var pub = data.publications;
      if (!pub) return;
      var r = pub.regions;
      svg.setAttribute("viewBox", "0 0 600 440");
      var circles = [
        { key: "hpc", cx: 235, cy: 170, label: "HPC", lx: 120, ly: 50 },
        { key: "vis", cx: 365, cy: 170, label: "Visualization", lx: 480, ly: 50 },
        { key: "hci", cx: 300, cy: 285, label: "HCI", lx: 300, ly: 432 }
      ];
      circles.forEach(function (ci) {
        svgEl("circle", { cx: ci.cx, cy: ci.cy, r: 125, fill: c[ci.key], "fill-opacity": 0.14, stroke: c[ci.key], "stroke-width": 2 }, svg);
      });
      circles.forEach(function (ci) {
        text(svg, ci.lx, ci.ly, ci.label, { "font-size": 15, "font-weight": 700, "text-anchor": "middle" });
      });
      var regions = [
        { v: r.hpc, x: 160, y: 140, label: "HPC only" },
        { v: r.vis, x: 440, y: 140, label: "Visualization only" },
        { v: r.hci, x: 300, y: 370, label: "HCI only" },
        { v: r.hpc_vis, x: 300, y: 115, label: "HPC and visualization" },
        { v: r.hpc_hci, x: 212, y: 270, label: "HPC and HCI", empty: true },
        { v: r.vis_hci, x: 388, y: 270, label: "Visualization and HCI" },
        { v: r.all, x: 300, y: 210, label: "All three" }
      ];
      regions.forEach(function (g) {
        var t = text(svg, g.x, g.y, g.v, {
          "font-size": g.v >= 5 ? 34 : 26,
          "font-weight": 700,
          "text-anchor": "middle",
          class: g.empty ? "history-chart-muted" : ""
        });
        svgEl("title", {}, t).textContent = g.label + ": " + g.v + (g.v === 1 ? " person" : " people");
        text(svg, g.x, g.y + 16, g.label, { "font-size": 10.5, "text-anchor": "middle", class: "history-chart-muted" });
      });
    },

    clusters: function (svg, c) {
      var pub = data.publications;
      if (!pub) return;
      svg.setAttribute("viewBox", "0 0 600 400");
      var pos = {
        exascale: { x: 110, y: 205 },
        scivis: { x: 290, y: 100 },
        va: { x: 490, y: 110 },
        immersive: { x: 290, y: 290 },
        creativity: { x: 490, y: 300 }
      };
      var radius = {};
      pub.clusters.forEach(function (cl) {
        radius[cl.id] = 16 + Math.sqrt(cl.size) * 13;
      });
      pub.cluster_links.forEach(function (l) {
        var a = pos[l.a];
        var b = pos[l.b];
        if (!a || !b) return;
        svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: c.muted, "stroke-opacity": 0.55, "stroke-width": 1 + l.shared * 2.2, "stroke-linecap": "round" }, svg);
        var mx = (a.x + b.x) / 2;
        var my = (a.y + b.y) / 2;
        svgEl("rect", { x: mx - 30, y: my - 10, width: 60, height: 18, rx: 9, fill: c.surface, stroke: c.rule }, svg);
        text(svg, mx, my + 3.5, l.shared + " shared", { "font-size": 10.5, "text-anchor": "middle", class: "history-chart-muted" });
      });
      pub.clusters.forEach(function (cl) {
        var p = pos[cl.id];
        if (!p) return;
        var circle = svgEl("circle", { cx: p.x, cy: p.y, r: radius[cl.id], fill: c[cl.area], stroke: c.surface, "stroke-width": 3 }, svg);
        svgEl("title", {}, circle).textContent = cl.label + ": " + cl.size + " people";
        text(svg, p.x, p.y + 7, cl.size, { "font-size": 20, "font-weight": 700, "text-anchor": "middle", fill: "#fff", style: "fill:#fff" });
        var words = cl.label.split(" ");
        var half = Math.ceil(words.length / 2);
        var below = p.y + radius[cl.id] + 16;
        text(svg, p.x, below, words.slice(0, half).join(" "), { "font-size": 12, "font-weight": 600, "text-anchor": "middle" });
        text(svg, p.x, below + 14, words.slice(half).join(" "), { "font-size": 12, "font-weight": 600, "text-anchor": "middle" });
      });
    },

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
