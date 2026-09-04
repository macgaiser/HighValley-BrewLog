"""Abgeleitete Kennzahlen für einen Sud (IBU, Alkohol, Ausbeute, Kosten).

Diese Werte werden bewusst nicht in der Datenbank gespeichert, sondern bei
jedem Aufruf aus den Rohdaten (Schüttung, Hopfengaben, Gärverlauf, ...) neu
berechnet - so bleiben sie immer konsistent, wenn ein Sud nachträglich
bearbeitet wird.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app import formulas
from app.models import Batch, Settings


@dataclass
class BatchMetrics:
    total_grain_kg: float = 0.0
    total_hop_g: float = 0.0
    ibu_per_addition: dict[int, float] = field(default_factory=dict)
    ibu_total: float = 0.0
    mash_efficiency_percent: float | None = None
    og_plato: float | None = None
    latest_brix: float | None = None
    latest_fermentation_date: date | None = None
    attenuation_percent: float | None = None
    abv_percent: float | None = None
    abv_display: str | None = None
    ibu_is_recorded: bool = False
    abv_is_recorded: bool = False
    color_ebc: float | None = None
    color_is_recorded: bool = False
    malt_cost: float = 0.0
    hop_cost: float = 0.0
    yeast_cost: float = 0.0
    labor_cost: float = 0.0
    total_cost: float = 0.0
    cost_per_liter: float | None = None
    cost_per_0_5l: float | None = None
    cost_is_incomplete: bool = False


def compute_metrics(batch: Batch, settings: Settings) -> BatchMetrics:
    m = BatchMetrics()

    m.total_grain_kg = round(sum(g.amount_kg or 0 for g in batch.grain_additions), 3)
    m.total_hop_g = round(
        sum(h.amount_g or 0 for h in batch.hop_additions)
        + sum(d.amount_g or 0 for d in batch.dry_hop_additions),
        2,
    )

    # Stammwürze: gemessener Wert nach Kochen/Kühlung (mit Refraktometer-
    # Korrekturfaktor), sonst geplanter Wert, sonst nichts.
    if batch.post_boil_brix:
        m.og_plato = round(batch.post_boil_brix / settings.wort_correction_factor, 2)
    elif batch.target_og_plato:
        m.og_plato = batch.target_og_plato

    if m.og_plato and batch.target_volume_l:
        for hop in batch.hop_additions:
            ibu = formulas.tinseth_ibu(
                weight_g=hop.amount_g or 0,
                alpha_acid_percent=hop.alpha_acid_percent or 0,
                boil_time_min=hop.time_min or 0,
                batch_volume_l=batch.target_volume_l,
                og_plato=m.og_plato,
            )
            if hop.id is not None:
                m.ibu_per_addition[hop.id] = ibu
            m.ibu_total += ibu
        m.ibu_total = round(m.ibu_total, 1)

    if not m.ibu_total and batch.recorded_ibu:
        m.ibu_total = batch.recorded_ibu
        m.ibu_is_recorded = True

    if m.og_plato and batch.target_volume_l and m.total_grain_kg:
        m.mash_efficiency_percent = formulas.mash_efficiency_percent(
            batch_volume_l=batch.target_volume_l,
            og_plato=m.og_plato,
            total_grain_kg=m.total_grain_kg,
            correction_factor=settings.mash_efficiency_correction_factor,
        )

    # Bierfarbe: nur berechenbar, wenn jede Schüttungsposition mit einem
    # Malz-Lagerartikel verknüpft ist, an dem eine Eigenfarbe (EBC) hinterlegt
    # wurde - sonst würde eine fehlende Position die Farbe unterschätzen.
    if (
        batch.target_volume_l
        and batch.grain_additions
        and all(g.inventory_item and g.inventory_item.color_ebc for g in batch.grain_additions)
    ):
        grain_colors = [(g.amount_kg or 0, g.inventory_item.color_ebc) for g in batch.grain_additions]
        m.color_ebc = formulas.beer_color_ebc(grain_colors, batch.target_volume_l)

    if not m.color_ebc and batch.color_ebc:
        m.color_ebc = batch.color_ebc
        m.color_is_recorded = True

    fermentation_readings = [e for e in batch.fermentation_entries if e.brix is not None]
    if fermentation_readings and m.og_plato:
        latest = fermentation_readings[-1]
        m.latest_brix = latest.brix
        m.latest_fermentation_date = latest.entry_date
        m.attenuation_percent = formulas.attenuation_percent(m.og_plato, latest.brix)
        m.abv_percent = formulas.abv_from_brix(m.og_plato, latest.brix)
        m.abv_display = f"{m.abv_percent:.1f} Vol.-%"

    if m.abv_display is None and batch.recorded_abv_text:
        m.abv_display = batch.recorded_abv_text
        m.abv_is_recorded = True

    m.malt_cost = round(m.total_grain_kg * settings.malt_cost_per_kg, 2)
    m.hop_cost = round(m.total_hop_g * settings.hop_cost_per_100g / 100, 2)
    m.yeast_cost = settings.yeast_flat_cost if batch.yeast_additions else 0.0
    total_minutes = sum(t.planned_duration_min or 0 for t in batch.brew_day_tasks)
    m.labor_cost = round(total_minutes / 60 * settings.labor_cost_per_hour, 2)
    m.total_cost = round(m.malt_cost + m.hop_cost + m.yeast_cost + m.labor_cost, 2)

    if batch.target_volume_l:
        m.cost_per_liter = round(m.total_cost / batch.target_volume_l, 2)
        m.cost_per_0_5l = round(m.cost_per_liter / 2, 2)

    # Kein Brautag-Zeitplan hinterlegt -> Lohnkosten fehlen komplett in der
    # Summe, Kosten sind also eine Untergrenze, kein verlässlicher Wert.
    m.cost_is_incomplete = not batch.brew_day_tasks

    return m
