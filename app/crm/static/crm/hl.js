/* =====================================================================
   H & L Roofers CRM: the little JavaScript the pages need.
   Everything else is plain HTML from the server, styled by Bootstrap.
   ===================================================================== */

/* 1. Follow the phone's or computer's light or dark setting. Runs at once, before the page is drawn. */
(function () {
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  function set() { document.documentElement.setAttribute("data-bs-theme", dark.matches ? "dark" : "light"); }
  set();
  if (dark.addEventListener) dark.addEventListener("change", set);
})();

document.addEventListener("DOMContentLoaded", function () {
  document.addEventListener("click", function (event) {
    /* 2. Call, Text and Directions add a line to the record's history.
          The link itself still opens the phone's own app. */
    var link = event.target.closest("[data-touch]");
    if (link && navigator.sendBeacon) {
      var data = new FormData();
      data.append("csrfmiddlewaretoken", document.body.dataset.csrf);
      data.append("kind", link.dataset.kind);
      data.append("id", link.dataset.id);
      data.append("how", link.dataset.touch);
      navigator.sendBeacon(document.body.dataset.touchUrl, data);
    }
    /* 3. Buttons that ask first: <button data-confirm="Mark this job done?"> */
    var button = event.target.closest("[data-confirm]");
    if (button && !window.confirm(button.dataset.confirm)) event.preventDefault();
  });

  /* 4. On a phone, slide the stage bar sideways so the current step shows. */
  var current = document.querySelector(".hl-stage .cur");
  if (current) {
    var bar = current.parentNode;
    bar.scrollLeft = current.offsetLeft - bar.offsetLeft - bar.clientWidth / 2 + current.clientWidth / 2;
  }

  /* 5. Short messages such as "Saved" go away after a few seconds. */
  document.querySelectorAll(".toast.show").forEach(function (toast) {
    setTimeout(function () { toast.classList.remove("show"); }, 4500);
  });

  /* 6. The "select all" box on the import review list. */
  var all = document.querySelector("[data-check-all]");
  if (all) all.addEventListener("change", function () {
    document.querySelectorAll("input[name=note]").forEach(function (box) { box.checked = all.checked; });
  });
});
