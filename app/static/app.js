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
  }
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
