// Alumni page (/people/alumni/): draws the graduates timeline and adds search and filters to the directory.
// Each list item carries its CSV "alumni" value ("MS 03, PhD 07"); the latest degree year places it on the timeline.
(function () {
  const list = document.getElementById("alumni-list");
  const svg = document.getElementById("alumni-timeline");
  if (!list || !svg) return;

  const DEG_CLASS = { PhD: "phd", MS: "ms", MA: "ms", MFA: "mfa", BFA: "mfa", BS: "bs" };
  const DEG_ORDER = { phd: 0, ms: 1, mfa: 2, bs: 3 };
  const fullYear = yy => (yy >= 60 ? 1900 : 2000) + yy;

  const people = Array.from(list.children).map(li => {
    const degrees = [];
    let year = null;
    (li.dataset.alumni || "").replace(/\b(PhD|MS|MA|MFA|BFA|BS)\b(?:\s+(\d{2}))?/g, (_, deg, yy) => {
      degrees.push(deg);
      if (yy && (year === null || fullYear(+yy) > year)) year = fullYear(+yy);
    });
    const top = degrees.includes("PhD") ? "PhD" : degrees[degrees.length - 1];
    return { li, name: li.dataset.name || "", degrees, year, cls: top ? DEG_CLASS[top] : "ms",
             label: li.querySelector("strong").textContent.trim() };
  });

  // Timeline
  const state = { q: "", degree: "", decade: "", year: null };
  const dated = people.filter(p => p.year);
  const byYear = {};
  dated.forEach(p => (byYear[p.year] = byYear[p.year] || []).push(p));
  Object.values(byYear).forEach(a => a.sort((x, y) => DEG_ORDER[x.cls] - DEG_ORDER[y.cls]));
  const years = dated.map(p => p.year);
  const y0 = Math.floor(Math.min(...years) / 10) * 10, y1 = new Date().getFullYear();
  const col = 16, r = 5.5, gap = 1.6, padL = 8, padT = 8, padB = 24;
  const maxN = Math.max(...Object.values(byYear).map(a => a.length));
  const W = padL * 2 + (y1 - y0 + 1) * col, H = padT + maxN * (2 * r + gap) + padB;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  for (let y = y0; y <= y1; y++) {
    const x = padL + (y - y0) * col + col / 2;
    const g = el("g", { class: "alumni-year", "data-year": y, tabindex: byYear[y] ? 0 : -1 });
    if (y % 10 === 0) {
      g.appendChild(el("line", { x1: x, x2: x, y1: padT, y2: H - padB, class: "alumni-grid" }));
      const t = el("text", { x, y: H - 6, "text-anchor": "middle", class: "alumni-axis" });
      t.textContent = y;
      g.appendChild(t);
    }
    g.appendChild(el("rect", { x: x - col / 2, y: padT, width: col, height: H - padT - padB, class: "alumni-hit" }));
    (byYear[y] || []).forEach((p, i) => {
      const c = el("circle", { cx: x, cy: H - padB - r - 2 - i * (2 * r + gap), r, class: "alumni-deg-" + p.cls });
      const title = el("title", {});
      title.textContent = `${p.label}, ${p.li.dataset.alumni}`;
      c.appendChild(title);
      g.appendChild(c);
    });
    if (byYear[y]) {
      const pick = () => { state.year = state.year === y ? null : y; state.decade = ""; syncChips(); render(); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    }
    svg.appendChild(g);
  }

  // Directory filters
  const controls = document.getElementById("alumni-controls");
  const count = document.getElementById("alumni-count");
  controls.hidden = false;
  document.getElementById("alumni-search").addEventListener("input", e => { state.q = e.target.value.trim().toLowerCase(); render(); });
  controls.querySelectorAll(".alumni-chips").forEach(group => {
    group.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      state[group.dataset.filter] = b.dataset.value;
      if (group.dataset.filter === "decade") state.year = null;
      syncChips();
      render();
    });
  });
  function syncChips() {
    controls.querySelectorAll(".alumni-chips").forEach(group => {
      group.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.value === state[group.dataset.filter])));
    });
    svg.querySelectorAll(".alumni-year").forEach(g => g.classList.toggle("is-selected", +g.dataset.year === state.year));
  }
  function render() {
    let shown = 0;
    people.forEach(p => {
      const ok = (!state.q || p.name.includes(state.q))
        && (!state.degree || p.degrees.includes(state.degree) || (state.degree === "MS" && p.degrees.includes("MA"))
            || (state.degree === "MFA" && p.degrees.includes("BFA")))
        && (!state.decade || (state.decade === "none" ? !p.year : p.year && Math.floor(p.year / 10) * 10 === +state.decade))
        && (state.year === null || p.year === state.year);
      p.li.hidden = !ok;
      if (ok) shown++;
    });
    const scope = state.year !== null ? ` who graduated in ${state.year}` : "";
    count.textContent = `${shown} of ${people.length} alumni${scope}`;
  }
  render();
})();
