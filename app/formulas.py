"""Brautechnische Berechnungen.

Ersetzt die fehlerhaften Formeln der ursprünglichen Excel-Vorlage (u.a. eine
#NAME?-Alkoholformel, die eine Google-Sheets-only Funktion nutzte, sowie eine
dimensional unplausible Sudhausausbeute-Formel) durch dokumentierte
Standardformeln aus der Brauliteratur.

Quellen:
- Plato <-> spezifisches Gewicht: ASBC-Näherungsformel (Kunze, "Technologie
  Brauer & Mälzer")
- Refraktometer-Korrektur (Brix während der Gärung -> reales Extrakt):
  Sean Terrill, "New (and Improved?) Formula for Calculating Refractometer
  FG Results" (2011) - Standardformel, wie sie auch von Kleiner Brauhelfer,
  Brewer's Friend u.a. verwendet wird
- Alkohol aus realem Extrakt: Balling-Formel (ABW), umgerechnet in ABV
- IBU: Glenn Tinseth, "A Recreation of Ray Daniels' IBU Formula" (1997)
"""

from __future__ import annotations

import math


def plato_to_sg(plato: float) -> float:
    """Grad Plato -> spezifisches Gewicht (ASBC-Näherung)."""
    return 1 + (plato / (258.6 - ((plato / 258.2) * 227.1)))


def sg_to_plato(sg: float) -> float:
    """Spezifisches Gewicht -> Grad Plato (Standard-Kubikformel, ASBC)."""
    return (
        -616.868
        + 1111.14 * sg
        - 630.272 * sg**2
        + 135.997 * sg**3
    )


def real_extract_sg(og_brix: float, current_brix: float) -> float:
    """Reales Extrakt als spezifisches Gewicht, aus OG-Brix und aktueller
    Brix-Ablesung (Sean-Terrill-Refraktometerkorrektur, 2011).

    Ein Refraktometer zeigt während der Gärung zu hohe Werte, weil Alkohol
    das Licht anders bricht als gelöster Zucker. Diese Formel korrigiert das.
    """
    return (
        1.001843
        - 0.002318474 * og_brix
        - 0.000007775 * og_brix**2
        - 0.000000034 * og_brix**3
        + 0.00574 * current_brix
        + 0.00003344 * current_brix**2
        + 0.000000086 * current_brix**3
    )


def attenuation_percent(og_plato: float, current_brix: float) -> float:
    """Scheinbarer Vergärungsgrad (EVG) in Prozent, auf Basis des realen
    Extrakts."""
    if og_plato <= 0:
        return 0.0
    re_plato = max(0.0, sg_to_plato(real_extract_sg(og_plato, current_brix)))
    return round(min(100.0, max(0.0, (og_plato - re_plato) / og_plato * 100)), 1)


def abv_from_brix(og_plato: float, current_brix: float) -> float:
    """Alkoholgehalt (Vol.-%) aus OG (°Plato) und aktueller Brix-Messung.

    Nutzt die Refraktometer-Korrektur für das reale Restextrakt und dann die
    Balling-Formel für den Alkoholgehalt aus realem Extrakt.
    """
    re_sg = max(1.0, real_extract_sg(og_plato, current_brix))
    re_plato = max(0.0, sg_to_plato(re_sg))
    return abv_from_og_re_plato(og_plato, re_plato, re_sg)


def abv_from_og_re_plato(og_plato: float, re_plato: float, re_sg: float) -> float:
    """Alkoholgehalt (Vol.-%) aus Stammwürze und realem Extrakt (°Plato)."""
    if og_plato <= re_plato:
        return 0.0
    denom = 2.0665 - 0.010665 * og_plato
    if denom <= 0:
        return 0.0
    abw = (og_plato - re_plato) / denom  # Alkohol Gewichtsprozent
    abv = abw * re_sg / 0.794
    return round(max(0.0, abv), 2)


def tinseth_ibu(
    weight_g: float,
    alpha_acid_percent: float,
    boil_time_min: float,
    batch_volume_l: float,
    og_plato: float,
) -> float:
    """IBU-Beitrag einer einzelnen Hopfengabe nach der Tinseth-Formel (1997).

    utilization = 1.65 * 0.000125^(SG-1) * (1 - e^(-0.04*t)) / 4.15
    IBU = utilization * (Alphasäure_mg / Liter)
    """
    if weight_g <= 0 or alpha_acid_percent <= 0 or batch_volume_l <= 0:
        return 0.0
    og_sg = plato_to_sg(og_plato)
    bigness_factor = 1.65 * (0.000125 ** (og_sg - 1))
    boil_time_factor = (1 - math.exp(-0.04 * boil_time_min)) / 4.15
    utilization = bigness_factor * boil_time_factor
    aau_mg_per_l = (weight_g * (alpha_acid_percent / 100) * 1000) / batch_volume_l
    return round(utilization * aau_mg_per_l, 1)


def mash_efficiency_percent(
    batch_volume_l: float,
    og_plato: float,
    total_grain_kg: float,
    assumed_extract_potential: float = 0.80,
) -> float:
    """Sudhausausbeute in Prozent.

    Verhältnis von tatsächlich gelöstem Extrakt zur theoretisch im Malz
    enthaltenen Extraktmenge (Kunze, "Technologie Brauer & Mälzer").

    `assumed_extract_potential` ist eine Annahme (Standard: 80 % feine
    Schrotausbeute für eine durchschnittliche Malzschüttung), da diese App
    aktuell keine malzsortenspezifischen Ausbeutewerte pflegt.
    """
    if total_grain_kg <= 0 or og_plato <= 0:
        return 0.0
    og_sg = plato_to_sg(og_plato)
    extract_mass_kg = batch_volume_l * og_sg * (og_plato / 100)
    theoretical_extract_kg = total_grain_kg * assumed_extract_potential
    if theoretical_extract_kg <= 0:
        return 0.0
    return round(extract_mass_kg / theoretical_extract_kg * 100, 1)
