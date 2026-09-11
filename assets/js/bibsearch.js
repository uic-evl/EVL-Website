// Filter the publications list as the user types.
//
// The page holds ~800 entries and ~46k DOM nodes, so the filter is built to
// touch the DOM as little as possible:
//   - every entry's text is lower-cased once at load and kept in an array,
//   - a pass only toggles the class on entries whose visibility changes,
//   - search-term highlighting only walks the entries that matched.
document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("bibsearch");
  if (!input) return;

  const HIDDEN_CLASS = "unloaded";
  const setHidden = (el, hidden) => el.classList.toggle(HIDDEN_CLASS, hidden);

  // One record per entry: element, searchable text, current state.
  const entries = Array.from(document.querySelectorAll(".bibliography > li")).map((el) => ({
    el,
    text: el.textContent.toLowerCase(),
    hidden: el.classList.contains(HIDDEN_CLASS),
  }));

  // Entries grouped by their parent list, so a list can be hidden when it is empty.
  const entriesByList = new Map();
  for (const entry of entries) {
    const list = entry.el.parentElement;
    if (!entriesByList.has(list)) entriesByList.set(list, []);
    entriesByList.get(list).push(entry);
  }

  // Each h2 (year) owns everything up to the next h2: optional h3 sub-headings and their lists.
  const groups = Array.from(document.querySelectorAll("h2.bibliography")).map((h2) => {
    const lists = [];
    let node = h2.nextElementSibling;
    while (node && node.tagName !== "H2") {
      if (node.tagName === "OL") lists.push(node);
      node = node.nextElementSibling;
    }
    return { h2, lists };
  });

  const highlight = (term, matched) => {
    if (!CSS.highlights) return; // Custom Highlight API not supported (e.g. older Firefox)
    CSS.highlights.delete("search");
    // A one-character term matches tens of thousands of places; not worth highlighting.
    if (term.length < 2) return;

    const ranges = [];
    for (const { el } of matched) {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const text = node.textContent.toLowerCase();
        let index = text.indexOf(term);
        while (index >= 0) {
          const range = new Range();
          range.setStart(node, index);
          range.setEnd(node, index + term.length);
          ranges.push(range);
          index = text.indexOf(term, index + term.length);
        }
      }
    }
    if (ranges.length > 0) CSS.highlights.set("search", new Highlight(...ranges));
  };

  let lastTerm = null;
  const filterItems = (term) => {
    if (term === lastTerm) return;
    lastTerm = term;

    const matched = [];
    for (const entry of entries) {
      const hide = term !== "" && !entry.text.includes(term);
      if (hide !== entry.hidden) {
        entry.hidden = hide;
        setHidden(entry.el, hide);
      }
      if (!hide) matched.push(entry);
    }

    for (const { h2, lists } of groups) {
      let groupVisible = false;
      for (const list of lists) {
        const visible = (entriesByList.get(list) || []).some((entry) => !entry.hidden);
        setHidden(list, !visible);
        const heading = list.previousElementSibling; // h3 sub-heading, if any
        if (heading && heading !== h2) setHidden(heading, !visible);
        if (visible) groupVisible = true;
      }
      setHidden(h2, !groupVisible);
    }

    highlight(term, matched);
  };

  const updateInputField = () => {
    const hashValue = decodeURIComponent(window.location.hash.substring(1)); // Remove the '#' character
    input.value = hashValue;
    filterItems(hashValue.toLowerCase());
  };

  // Only filter once the user has paused typing.
  let timeoutId;
  input.addEventListener("input", function () {
    clearTimeout(timeoutId);
    const term = this.value.toLowerCase();
    timeoutId = setTimeout(() => filterItems(term), 150);
  });

  window.addEventListener("hashchange", updateInputField); // Update the filter when the hash changes

  updateInputField(); // Update filter when page loads
});
