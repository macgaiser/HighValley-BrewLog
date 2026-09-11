// Generische Zeilen-Verwaltung für die dynamischen Tabellen im Sud-Formular.
// Jede Sektion hat: ein <tbody data-rows="NAME">, ein <template data-row-template="NAME">
// und einen Button [data-add-row="NAME"].

document.addEventListener("click", (event) => {
  const addBtn = event.target.closest("[data-add-row]");
  if (addBtn) {
    event.preventDefault();
    const name = addBtn.getAttribute("data-add-row");
    const tbody = document.querySelector(`[data-rows="${name}"]`);
    const template = document.querySelector(`[data-row-template="${name}"]`);
    if (tbody && template) {
      const clone = template.content.cloneNode(true);
      tbody.appendChild(clone);
    }
    updateColorEbcAutoState();
    return;
  }

  const removeBtn = event.target.closest("[data-remove-row]");
  if (removeBtn) {
    event.preventDefault();
    removeBtn.closest("tr").remove();
    updateColorEbcAutoState();
    return;
  }

  const upBtn = event.target.closest("[data-move-up]");
  if (upBtn) {
    event.preventDefault();
    const row = upBtn.closest("tr");
    const prev = row.previousElementSibling;
    if (prev) row.parentNode.insertBefore(row, prev);
    return;
  }

  const downBtn = event.target.closest("[data-move-down]");
  if (downBtn) {
    event.preventDefault();
    const row = downBtn.closest("tr");
    const next = row.nextElementSibling;
    if (next) row.parentNode.insertBefore(next, row);
  }
});

// Brautag-Zeitplan-Dialog: Dauer aus Beginn/Ende berechnen, sobald beide
// <input type="time">-Felder einer Zeile gefuellt sind (manuelle Eingabe
// der Dauer bleibt trotzdem jederzeit moeglich, wird nur bei einer
// Aenderung von Beginn/Ende ueberschrieben).
document.addEventListener("input", (event) => {
  const timeField = event.target.closest("[data-schedule-start], [data-schedule-end]");
  if (!timeField) return;
  const row = timeField.closest("[data-schedule-row]");
  if (!row) return;
  const start = row.querySelector("[data-schedule-start]").value;
  const end = row.querySelector("[data-schedule-end]").value;
  if (!start || !end) return;
  const [startH, startM] = start.split(":").map(Number);
  const [endH, endM] = end.split(":").map(Number);
  let minutes = (endH * 60 + endM) - (startH * 60 + startM);
  if (minutes < 0) minutes += 24 * 60; // Ende nach Mitternacht
  row.querySelector("[data-schedule-duration]").value = minutes;
});

// Sud-Übersicht: Checkbox "Vergleichen" je Zeile - hebt die Zeile farblich
// hervor und haelt den Zaehler/Aktivierungszustand des "Vergleichen"-Buttons
// oben im Seitenkopf synchron (Button ist per form="compare-form" mit den
// verstreuten Checkboxen verbunden, siehe batch_list.html).
function updateCompareButton() {
  const btn = document.getElementById("compare-submit");
  if (!btn) return;
  const count = document.querySelectorAll("[data-compare-checkbox]:checked").length;
  btn.disabled = count === 0;
  btn.textContent = count > 0 ? `Vergleichen (${count})` : "Vergleichen";
}
document.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-compare-checkbox]");
  if (!checkbox) return;
  checkbox.closest("tr").classList.toggle("row-selected", checkbox.checked);
  updateCompareButton();
});
updateCompareButton();

// Farbe (EBC) in Stammdaten: wird ausgegraut/schreibgeschuetzt, sobald die
// automatische Berechnung aus der Schüttung greift (jede Position mit einem
// Malz-Lagerartikel mit hinterlegter Eigenfarbe verknuepft - siehe dieselbe
// Bedingung in batch_calc.compute_metrics()). Verhindert, dass man aus
// Gewohnheit schon vor dem Ausfuellen der Schüttung (weiter unten im
// Formular) einen EBC-Wert eintraegt, der dann ungenutzt bleibt.
function updateColorEbcAutoState() {
  const input = document.getElementById("color-ebc-input");
  const hint = document.getElementById("color-ebc-auto-hint");
  const infoBtn = document.getElementById("color-ebc-info-btn");
  if (!input || !hint || !infoBtn) return;
  const linked = Array.from(document.querySelectorAll("[data-grain-select]")).map((select) => {
    if (!select.value) return false;
    const opt = select.options[select.selectedIndex];
    return !!(opt && opt.dataset.ebc);
  });
  const auto = linked.length > 0 && linked.every(Boolean);
  input.readOnly = auto;
  infoBtn.hidden = !auto;
  if (!auto) hint.hidden = true; // Info-Button verschwindet -> Text mit zuklappen
}
document.addEventListener("change", (event) => {
  if (event.target.closest("[data-grain-select]")) updateColorEbcAutoState();
});
document.addEventListener("click", (event) => {
  if (event.target.closest("#color-ebc-info-btn")) {
    const hint = document.getElementById("color-ebc-auto-hint");
    hint.hidden = !hint.hidden;
  }
});
updateColorEbcAutoState();

// Datumsfelder zeigen ihr Format sonst je nach Browser-/Systemsprache an
// (z.B. mm/dd/yyyy) statt einheitlich dd.mm.yyyy - flatpickr übernimmt die
// Anzeige, das eigentliche Feld sendet weiterhin ISO-Format (yyyy-mm-dd).
if (window.flatpickr) {
  document.querySelectorAll('input[type="date"]').forEach((el) => {
    flatpickr(el, {
      altInput: true,
      altFormat: "d.m.Y",
      dateFormat: "Y-m-d",
      locale: "de",
      allowInput: true,
    });
  });
}
