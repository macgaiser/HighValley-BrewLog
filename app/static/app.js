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
    return;
  }

  const removeBtn = event.target.closest("[data-remove-row]");
  if (removeBtn) {
    event.preventDefault();
    removeBtn.closest("tr").remove();
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

// Brautag-Zeitplan-Dialog: Beginn/Ende sind reine HH:MM-Textfelder statt
// <input type="time"> - das native Zeitfeld zeigt je nach Geraet/Browser
// AM/PM statt 24h an (browser-/OS-Locale, laesst sich nicht per lang-Attribut
// erzwingen). Ziffern werden beim Tippen automatisch zu "HH:MM" formatiert;
// sobald beide Felder gefuellt sind, wird daraus die Dauer berechnet
// (manuelle Eingabe der Dauer bleibt trotzdem jederzeit moeglich, wird nur
// bei einer Aenderung von Beginn/Ende ueberschrieben).
document.addEventListener("input", (event) => {
  const timeField = event.target.closest("[data-time-input]");
  if (!timeField) return;
  const digits = timeField.value.replace(/\D/g, "").slice(0, 4);
  timeField.value = digits.length > 2 ? digits.slice(0, 2) + ":" + digits.slice(2) : digits;

  const row = timeField.closest("[data-schedule-row]");
  if (!row) return;
  const start = row.querySelector("[data-schedule-start]").value;
  const end = row.querySelector("[data-schedule-end]").value;
  if (start.length !== 5 || end.length !== 5) return;
  const [startH, startM] = start.split(":").map(Number);
  const [endH, endM] = end.split(":").map(Number);
  let minutes = (endH * 60 + endM) - (startH * 60 + startM);
  if (minutes < 0) minutes += 24 * 60; // Ende nach Mitternacht
  row.querySelector("[data-schedule-duration]").value = minutes;
});

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
