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

/* 7. The proposal builder: add a line, remove a line, add an item from the Price Book, work out
      quantity × price for each, and keep the total. The server works it all out again when the form is saved. */
document.addEventListener("DOMContentLoaded", function () {
  var form = document.querySelector("[data-builder]");
  if (!form) return;
  var rows = form.querySelector("[data-rows]");
  function number(box) {
    var value = parseFloat(box.value.replace(/[$,]/g, ""));
    return isNaN(value) ? null : value;
  }
  function plain(value) {                       /* 1100 -> "1100", 83.75 -> "83.75": what goes back into a box */
    return (Math.round(value * 100) / 100).toFixed(2).replace(/\.00$/, "");
  }
  function line(row) {                          /* a quantity and a price for each: the amount is worked out and cannot be typed */
    var quantity = number(row.querySelector("[name=quantity]")), each = number(row.querySelector("[name=each]"));
    var amount = row.querySelector("[name=amount]");
    if (each !== null && quantity === null) quantity = 1;
    var worked = quantity !== null && each !== null;
    if (worked) amount.value = plain(quantity * each);
    amount.readOnly = worked;
  }
  function total() {
    var sum = 0;
    rows.querySelectorAll("[data-row]").forEach(function (row) {
      line(row);
      var amount = number(row.querySelector("[name=amount]"));
      if (amount !== null) sum += amount;
    });
    form.querySelector("[data-total]").textContent = (sum < 0 ? "−$" : "$") +
      Math.abs(sum).toLocaleString("en-US", { minimumFractionDigits: sum % 1 ? 2 : 0, maximumFractionDigits: 2 });
  }
  function addRow(item) {
    var row = rows.querySelector("[data-row]").cloneNode(true);
    row.querySelectorAll("input").forEach(function (box) { box.value = ""; box.readOnly = false; });
    if (item) {
      row.querySelector("[name=text]").value = item.text;
      row.querySelector("[name=quantity]").value = "1";
      row.querySelector("[name=unit]").value = item.unit || "";
      row.querySelector("[name=each]").value = item.each;
    }
    var unit = row.querySelector("[data-unit]");
    unit.textContent = item && item.unit ? item.unit : "";
    unit.classList.toggle("d-none", !(item && item.unit));
    rows.appendChild(row);
    total();
    var focus = row.querySelector(item ? "[name=quantity]" : "[name=text]");
    focus.focus();
    if (item) focus.select();                   /* ready to type how many */
  }
  form.addEventListener("input", total);
  form.addEventListener("click", function (event) {
    if (event.target.closest("[data-add-row]")) addRow();
    var remove = event.target.closest("[data-remove-row]");
    if (remove && rows.querySelectorAll("[data-row]").length > 1) { remove.closest("[data-row]").remove(); total(); }
  });
  var picker = form.querySelector("[data-add-item]");
  if (picker) picker.addEventListener("change", function () {
    var item = picker.options[picker.selectedIndex];
    if (item.dataset.text) addRow({ text: item.dataset.text, unit: item.dataset.unit, each: item.dataset.each });
    picker.selectedIndex = 0;
  });
  total();
});

/* 8. A "Copy" button next to a box: <button data-copy="#acceptLink"> */
document.addEventListener("click", function (event) {
  var button = event.target.closest("[data-copy]");
  if (!button || !navigator.clipboard) return;
  navigator.clipboard.writeText(document.querySelector(button.dataset.copy).value);
});

/* 9. A list that acts as soon as something is picked: <select data-submit-on-change> */
document.addEventListener("change", function (event) {
  if (event.target.matches("[data-submit-on-change]") && event.target.value !== "") event.target.form.submit();
});


/* 10. Charts: the small box that names a bar when the pointer or the keyboard is on it (Bootstrap's tooltip) */
document.addEventListener("DOMContentLoaded", function () {
  if (!window.bootstrap) return;
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (mark) { new bootstrap.Tooltip(mark, { container: "body" }); });
});

/* 11. The data editor: a box that was changed turns yellow, and the button counts the changes */
function countEdits(form) {
  var changed = 0;
  form.querySelectorAll("[data-was]").forEach(function (box) {
    var differs = box.value !== box.dataset.was;
    box.classList.toggle("border-warning", differs);
    box.classList.toggle("bg-warning-subtle", differs);
    if (differs) changed += 1;
  });
  form.querySelector("[data-count]").textContent = changed;
}
document.addEventListener("input", function (event) {
  var form = event.target.closest("[data-editor]");
  if (form) countEdits(form);
});
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-editor]").forEach(countEdits);
});

/* 12. Hide and show a section of a record page (a lead, an account, an opportunity, a job).
   The arrow at the top left of a section's title folds the section away, and opens it again.
   The choice is remembered on this phone or computer, for that section on every record of the same kind.
   A section is marked in the page with <h2 data-section="history">. */
document.addEventListener("DOMContentLoaded", function () {
  var kind = location.pathname.split("/")[1] || "", words = document.body.dataset;
  function hiddenBefore(key) { try { return localStorage.getItem(key) === "hidden"; } catch (e) { return false; } }
  function remember(key, hidden) {
    try { if (hidden) localStorage.setItem(key, "hidden"); else localStorage.removeItem(key); } catch (e) { /* a private window: not remembered */ }
  }
  document.querySelectorAll("h2[data-section]").forEach(function (title, n) {
    var body = title.closest(".card-body");
    if (!body) return;
    var head = title.parentElement === body ? title : title.parentElement;      // the title, or the row it sits in
    var rest = document.createElement("div"), key = "hl-hide:" + kind + ":" + title.dataset.section;
    rest.id = "section-" + n;
    while (head.nextSibling) rest.appendChild(head.nextSibling);
    body.appendChild(rest);
    var arrow = document.createElement("button");
    arrow.type = "button";
    arrow.className = "btn btn-link p-0 me-1 hl-fold";
    arrow.setAttribute("aria-controls", rest.id);
    arrow.innerHTML = '<svg class="hl-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
    title.insertBefore(arrow, title.firstChild);
    function show(open) {
      rest.hidden = !open;
      body.classList.toggle("hl-folded", !open);
      arrow.setAttribute("aria-expanded", open ? "true" : "false");
      arrow.setAttribute("aria-label", (open ? words.hide : words.show) + ": " + title.textContent.trim());
      arrow.title = open ? words.hide : words.show;
    }
    show(!hiddenBefore(key));
    arrow.addEventListener("click", function () {
      var open = rest.hidden;
      show(open);
      remember(key, !open);
    });
  });
});
