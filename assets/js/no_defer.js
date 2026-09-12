// add bootstrap classes to tables
$(document).ready(function () {
  // Follow the theme actually applied to the page (data-theme is only set when the
  // site's dark mode is enabled), not the device preference: with dark mode disabled
  // the page stays light, and a dark table would render white text on it.
  const pageTheme = document.documentElement.getAttribute("data-theme");
  $("table").each(function () {
    if (pageTheme == "dark") {
      $(this).addClass("table-dark");
    } else {
      $(this).removeClass("table-dark");
    }

    // only select tables that are not inside an element with "news" (about page) or "card" (cv page) class
    if (
      $(this).parents('[class*="news"]').length == 0 &&
      $(this).parents('[class*="card"]').length == 0 &&
      $(this).parents('[class*="archive"]').length == 0 &&
      $(this).parents("code").length == 0
    ) {
      // make table use bootstrap-table
      $(this).attr("data-toggle", "table");
      // add some classes to make the table look better
      // $(this).addClass('table-sm');
      $(this).addClass("table-hover");
    }
  });
});
