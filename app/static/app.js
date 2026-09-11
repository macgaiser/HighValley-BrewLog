// Generische Info-Buttons: ein <button class="info-btn" data-info-toggle="ID">i</button>
// oeffnet den Hinweistext mit dieser ID als schwebendes Popup in der Naehe
// des Buttons (position:fixed, ueber getBoundingClientRect platziert), statt
// ihn im Fliesstext einzublenden - fuer laengere Erklaerungen, die nicht
// staendig im Weg stehen sollen, aber bei Bedarf griffbereit sind. Es ist
// immer nur ein Popup gleichzeitig offen; Klick auf einen anderen Info-
// Button, in ein Feld oder sonst irgendwohin schliesst das offene wieder.
function closeInfoPopovers() {
  document.querySelectorAll(".info-popover:not([hidden])").forEach((el) => {
    el.hidden = true;
  });
}
function positionInfoPopover(btn, popover) {
  const rect = btn.getBoundingClientRect();
  popover.style.left = "0px";
  popover.style.top = "0px";
  popover.hidden = false;
  const popRect = popover.getBoundingClientRect();
  let left = rect.left;
  const maxLeft = window.innerWidth - popRect.width - 8;
  if (left > maxLeft) left = Math.max(8, maxLeft);
  let top = rect.bottom + 6;
  const maxTop = window.innerHeight - popRect.height - 8;
  if (top > maxTop) top = Math.max(8, rect.top - popRect.height - 6);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}
document.addEventListener("click", (event) => {
  const infoBtn = event.target.closest("[data-info-toggle]");
  if (infoBtn) {
    const target = document.getElementById(infoBtn.getAttribute("data-info-toggle"));
    if (!target) return;
    const wasOpen = !target.hidden;
    closeInfoPopovers();
    if (!wasOpen) positionInfoPopover(infoBtn, target);
    event.stopPropagation();
    return;
  }
  if (!event.target.closest(".info-popover")) closeInfoPopovers();
});

// Würzekochen: Alpha (%) wird beim Auswählen eines Lagerartikels einmalig
// aus dessen hinterlegter Alphasäure übernommen - nur in dem Moment der
// Auswahl, keine dauerhafte Bindung. Manuelle Änderungen danach bleiben
// unangetastet, und spätere Änderungen am Lagerartikel wirken sich nicht
// rückwirkend auf bereits gespeicherte Suden aus (der Wert landet als
// eigenstaendiger Schnappschuss in HopAddition.alpha_acid_percent).
document.addEventListener("change", (event) => {
  const select = event.target.closest('select[name="hop_inventory_id"]');
  if (!select) return;
  const opt = select.options[select.selectedIndex];
  const alpha = opt ? opt.dataset.alpha : "";
  if (alpha) {
    const alphaInput = select.closest("tr").querySelector('input[name="hop_alpha"]');
    if (alphaInput) alphaInput.value = alpha;
  }
  updateIbuPreviews();
});

// Würzekochen: IBU-Beitrag je Zeile nach der Tinseth-Formel, live im
// Bearbeiten-Formular berechnet (JS-Nachbau von formulas.tinseth_ibu) -
// auf Basis der geplanten Stammwürze, da der gemessene Wert ("nach dem
// Kochen") in diesem Formular gar nicht mehr gepflegt wird (eigener
// Dialog auf der Sud-Detailseite).
function platoToSg(plato) {
  return 1 + plato / (258.6 - (plato / 258.2) * 227.1);
}
function tinsethIbu(weightG, alphaPercent, boilTimeMin, batchVolumeL, ogPlato) {
  if (!(weightG > 0) || !(alphaPercent > 0) || !(batchVolumeL > 0) || !(ogPlato > 0)) return null;
  const ogSg = platoToSg(ogPlato);
  const bignessFactor = 1.65 * Math.pow(0.000125, ogSg - 1);
  const boilTimeFactor = (1 - Math.exp(-0.04 * boilTimeMin)) / 4.15;
  const utilization = bignessFactor * boilTimeFactor;
  const aauMgPerL = (weightG * (alphaPercent / 100) * 1000) / batchVolumeL;
  return Math.round(utilization * aauMgPerL * 10) / 10;
}
function updateIbuPreviews() {
  const rows = document.querySelectorAll('tbody[data-rows="hop"] tr');
  if (!rows.length) return;
  const batchVolumeL = parseFloat(document.querySelector('input[name="target_volume_l"]')?.value);
  const ogPlato = parseFloat(document.querySelector('input[name="target_og_plato"]')?.value);
  rows.forEach((row) => {
    const preview = row.querySelector("[data-ibu-preview]");
    if (!preview) return;
    const weightG = parseFloat(row.querySelector('input[name="hop_amount_g"]')?.value);
    const alphaPercent = parseFloat(row.querySelector('input[name="hop_alpha"]')?.value);
    const boilTimeMin = parseFloat(row.querySelector('input[name="hop_time_min"]')?.value) || 0;
    const ibu = tinsethIbu(weightG, alphaPercent, boilTimeMin, batchVolumeL, ogPlato);
    preview.textContent = ibu === null ? "–" : ibu.toFixed(1);
  });
}
document.addEventListener("input", (event) => {
  if (
    event.target.matches(
      'input[name="hop_amount_g"], input[name="hop_alpha"], input[name="hop_time_min"], input[name="target_volume_l"], input[name="target_og_plato"]'
    )
  ) {
    updateIbuPreviews();
  }
});
updateIbuPreviews();

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
    updateIbuPreviews();
    return;
  }

  const removeBtn = event.target.closest("[data-remove-row]");
  if (removeBtn) {
    event.preventDefault();
    removeBtn.closest("tr").remove();
    updateColorEbcAutoState();
    updateIbuPreviews();
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
