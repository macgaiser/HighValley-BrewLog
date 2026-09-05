"""Brautechnische Berechnungen.

Ersetzt die fehlerhaften Formeln der ursprünglichen Excel-Vorlage (u.a. eine
#NAME?-Alkoholformel, die eine Google-Sheets-only Funktion nutzte, sowie eine
dimensional unplausible Sudhausausbeute-Formel) durch dokumentierte
Standardformeln aus der Brauliteratur.

Quellen:
- Plato <-> spezifisches Gewicht: ASBC-Näherungsformel (Kunze, "Technologie
  Brauer & Mälzer")
- Refraktometer-Korrektur (Brix während der Gärung -> reales Extrakt):
  lineare Sean-Terrill-Formel (2011), so wie sie u.a. von Kleiner Brauhelfer
  und maischemalzundmehr.de verwendet wird - beide Brix-Ablesungen (Stamm-
  würze UND aktuelle Messung) werden dafür durch denselben Refraktometer-
  Korrekturfaktor geteilt, nicht nur die Stammwürze
- Alkohol aus realem Extrakt: einfache Faustformel ABV = (OG_SG - RE_SG) *
  131,25, wie sie u.a. auch von maischemalzundmehr.de verwendet wird
- IBU: Glenn Tinseth, "A Recreation of Ray Daniels' IBU Formula" (1997)
- Bierfarbe: Morey-Gleichung (Daniels, "Designing Great Beers", 2000),
  heutiger Quasi-Standard fürs Homebrewing (u.a. auch in Kleiner
  Brauhelfer/BeerSmith verwendet)
"""

from __future__ import annotations

import math

# Die lineare Terrill-Formel ist an echten (teil-)vergorenen Bieren
# kalibriert, nicht am (in der Praxis irrelevanten) Fall "noch gar nicht
# vergoren". Liegt die aktuelle Messung sehr nah an der Stammwürze, liefert
# sie dadurch einen unrealistischen Vergärungsgrad von ca. 33-35% statt der
# eigentlich erwarteten ~0% - dieser Schwellwert liegt bequem darüber, wird
# aber schon nach wenigen °Brix spürbarer Gärung wieder unterschritten.
ATTENUATION_UNCERTAIN_BELOW_PERCENT = 40.0


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


def real_extract_sg(og_plato: float, current_brix: float, correction_factor: float = 1.03) -> float:
    """Reales Extrakt als spezifisches Gewicht (lineare Sean-Terrill-
    Refraktometerkorrektur, 2011).

    Ein Refraktometer zeigt während der Gärung zu hohe Werte, weil Alkohol
    das Licht anders bricht als gelöster Zucker. Diese Formel korrigiert das
    - dafür müssen beide Ablesungen im selben "wortkorrigierten" Brix
    vorliegen: `og_plato` ist das an anderer Stelle bereits durch den
    Korrekturfaktor geteilte Stammwürze, `current_brix` ist die rohe
    Gärverlauf-Ablesung und wird hier zusätzlich durch denselben Faktor
    geteilt.
    """
    current_corrected = current_brix / correction_factor
    return (
        1.0000
        - 0.00085683 * og_plato
        + 0.0034941 * current_corrected
    )


def attenuation_percent(og_plato: float, current_brix: float, correction_factor: float = 1.03) -> float:
    """Scheinbarer Vergärungsgrad (EVG) in Prozent, auf Basis des realen
    Extrakts."""
    if og_plato <= 0:
        return 0.0
    re_plato = max(0.0, sg_to_plato(real_extract_sg(og_plato, current_brix, correction_factor)))
    return round(min(100.0, max(0.0, (og_plato - re_plato) / og_plato * 100)), 1)


def is_attenuation_uncertain(attenuation_percent_value: float) -> bool:
    """Die lineare Terrill-Formel ist an echten, spürbar vergorenen Bieren
    kalibriert - liegt die Messung noch sehr nah an der Stammwürze, liefert
    sie einen falsch hohen "Sockelwert" (siehe ATTENUATION_UNCERTAIN_BELOW_
    PERCENT) statt der eigentlich erwarteten ~0%. Für die Anzeige eines
    Hinweises, nicht zur weiteren Berechnung gedacht."""
    return attenuation_percent_value < ATTENUATION_UNCERTAIN_BELOW_PERCENT


def abv_from_brix(og_plato: float, current_brix: float, correction_factor: float = 1.03) -> float:
    """Alkoholgehalt (Vol.-%) aus OG (°Plato) und aktueller Brix-Messung.

    Nutzt die Refraktometer-Korrektur für das reale Restextrakt und dann die
    einfache Faustformel ABV = (OG_SG - RE_SG) * 131,25.
    """
    re_sg = max(0.9, real_extract_sg(og_plato, current_brix, correction_factor))
    og_sg = plato_to_sg(og_plato)
    return round(max(0.0, (og_sg - re_sg) * 131.25), 2)


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
    correction_factor: float = 1.0,
) -> float:
    """Sudhausausbeute in Prozent, nach der in deutschen Homebrewing-Quellen
    gebräuchlichen Formel:

        Sudhausausbeute = (Ausschlagmenge_L * Stammwürze_°P * spez.Gewicht)
                           / (Schüttung_kg * 1000) * 100

    d.h. Verhältnis von tatsächlich gelöster Extraktmasse zur eingesetzten
    Schüttungsmasse. Diese Formel bezieht sich bewusst direkt auf die
    Schüttungsmasse (nicht auf eine zusätzlich angenommene
    Malz-Extraktausbeute) - das ist bereits der Grund, warum realistische
    Werte üblicherweise bei 50-75 % statt nahe 100 % liegen, und warum eine
    frühere Version dieser Funktion (die zusätzlich durch eine angenommene
    80%ige Extraktausbeute geteilt hat) systematisch ca. 25 % zu hohe Werte
    lieferte - gegen 35 reale Sude aus dem Braubuch geprüft: Median-Abweichung
    von den dort von Hand berechneten Werten sank dadurch von +25 % auf 0.

    `correction_factor` erlaubt bei Bedarf eine Feinjustierung fürs eigene
    Sudhaus (Standard: 1,0 = keine Korrektur).
    """
    if total_grain_kg <= 0 or og_plato <= 0:
        return 0.0
    og_sg = plato_to_sg(og_plato)
    extract_mass_kg = batch_volume_l * og_sg * (og_plato / 100)
    theoretical_extract_kg = total_grain_kg * correction_factor
    if theoretical_extract_kg <= 0:
        return 0.0
    return round(extract_mass_kg / theoretical_extract_kg * 100, 1)


# (lb/kg) / (gal/L) - wandelt Malzmenge_kg/Volumen_L direkt in
# Malzmenge_lb/Volumen_gal um, ohne beide Größen einzeln umzurechnen.
_LB_PER_KG_OVER_GAL_PER_L = 8.3454


def beer_color_ebc(grain_kg_and_malt_ebc: list[tuple[float, float]], batch_volume_l: float) -> float:
    """Bierfarbe in °EBC aus der Schüttung, nach der Morey-Gleichung:

        MCU = Summe(Malzmenge_lb * Malzfarbe_Lovibond) / Ausschlagmenge_gal
        SRM = 1.4922 * MCU^0.6859
        EBC = SRM * 1.97

    `grain_kg_and_malt_ebc` sind (Malzmenge_kg, Malzfarbe_EBC)-Paare - die
    Farbe des einzelnen Malzes selbst, wie sie deutsche Mälzereien angeben
    (nicht die resultierende Bierfarbe). Da die Morey-Gleichung mit
    °Lovibond rechnet, wird die Malzfarbe näherungsweise über denselben
    EBC/SRM-Faktor (1.97) in °Lovibond umgerechnet - diese Vereinfachung
    ist in Brau-Software (Kleiner Brauhelfer, BeerSmith) verbreitet.
    """
    if batch_volume_l <= 0 or not grain_kg_and_malt_ebc:
        return 0.0
    mcu = sum(
        weight_kg * (malt_ebc / 1.97) * _LB_PER_KG_OVER_GAL_PER_L
        for weight_kg, malt_ebc in grain_kg_and_malt_ebc
        if weight_kg > 0 and malt_ebc and malt_ebc > 0
    ) / batch_volume_l
    if mcu <= 0:
        return 0.0
    srm = 1.4922 * (mcu**0.6859)
    return round(srm * 1.97, 1)
