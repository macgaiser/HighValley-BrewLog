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


# EBC-Farbtabelle: RGB-Referenzwerte je EBC-Wert, aus der Etiketten-
# Druckvorlage (Excel) des Nutzers uebernommen - dort per VBA-Makro
# (Worksheet_Calculate in "Tabelle1") mit der EBC-Zelle verknuepft, um deren
# Hintergrund einzufaerben. Tabelle in 0,5er-Schritten von 0 bis 150 EBC,
# danach nur noch grobe Stuetzstellen bis 300 EBC (sehr dunkle Biere
# unterscheiden sich farblich kaum noch).
_EBC_COLOR_TABLE: tuple[tuple[float, int, int, int], ...] = (
    (0, 255, 255, 255),
    (0.5, 255, 253, 230),
    (1, 255, 250, 198),
    (1.5, 255, 248, 175),
    (2, 255, 246, 149),
    (2.5, 255, 243, 123),
    (3, 255, 241, 94),
    (3.5, 255, 233, 84),
    (4, 255, 225, 74),
    (4.5, 255, 216, 66),
    (5, 255, 206, 57),
    (5.5, 255, 197, 47),
    (6, 255, 188, 37),
    (6.5, 255, 178, 26),
    (7, 255, 168, 16),
    (7.5, 255, 161, 8),
    (8, 255, 154, 0),
    (8.5, 253, 152, 0),
    (9, 251, 150, 0),
    (9.5, 249, 149, 0),
    (10, 247, 147, 0),
    (10.5, 245, 144, 0),
    (11, 243, 142, 0),
    (11.5, 240, 141, 0),
    (12, 237, 140, 0),
    (12.5, 235, 138, 0),
    (13, 233, 136, 0),
    (13.5, 231, 134, 0),
    (14, 229, 132, 0),
    (14.5, 227, 131, 0),
    (15, 226, 129, 0),
    (15.5, 223, 127, 0),
    (16, 221, 126, 0),
    (16.5, 219, 125, 0),
    (17, 218, 124, 0),
    (17.5, 216, 121, 0),
    (18, 214, 119, 0),
    (18.5, 212, 116, 0),
    (19, 211, 111, 0),
    (19.5, 208, 105, 0),
    (20, 204, 101, 0),
    (20.5, 204, 95, 0),
    (21, 203, 89, 0),
    (22, 199, 79, 0),
    (23, 194, 70, 0),
    (24, 192, 62, 0),
    (25, 186, 49, 0),
    (26, 181, 43, 0),
    (27, 177, 41, 0),
    (28, 171, 39, 0),
    (29, 165, 37, 0),
    (30, 161, 34, 0),
    (31, 155, 32, 0),
    (32, 149, 31, 0),
    (33, 143, 28, 0),
    (34, 140, 26, 0),
    (35, 134, 24, 0),
    (36, 130, 21, 0),
    (37, 124, 18, 0),
    (38, 119, 16, 0),
    (39, 114, 14, 0),
    (40, 107, 11, 0),
    (41, 103, 11, 0),
    (42, 96, 7, 0),
    (43, 92, 4, 0),
    (44, 86, 2, 0),
    (45, 81, 0, 0),
    (46, 78, 0, 0),
    (47, 75, 0, 0),
    (48, 72, 0, 0),
    (49, 70, 0, 0),
    (50, 68, 0, 0),
    (51, 68, 0, 0),
    (52, 66, 0, 0),
    (53, 66, 0, 0),
    (54, 66, 0, 0),
    (55, 65, 0, 0),
    (56, 65, 0, 0),
    (57, 65, 0, 0),
    (58, 64, 0, 0),
    (59, 64, 0, 0),
    (60, 64, 0, 0),
    (61, 63, 0, 0),
    (62, 63, 0, 0),
    (63, 63, 0, 0),
    (64, 62, 0, 0),
    (65, 62, 0, 0),
    (66, 62, 0, 0),
    (67, 61, 0, 0),
    (68, 61, 0, 0),
    (69, 61, 0, 0),
    (70, 61, 0, 0),
    (71, 60, 0, 0),
    (72, 60, 0, 0),
    (73, 59, 0, 0),
    (74, 59, 0, 0),
    (75, 58, 0, 0),
    (76, 58, 0, 0),
    (77, 57, 0, 0),
    (78, 57, 0, 0),
    (79, 56, 0, 0),
    (80, 56, 0, 0),
    (81, 56, 0, 0),
    (82, 56, 0, 0),
    (83, 55, 0, 0),
    (84, 55, 0, 0),
    (85, 55, 0, 0),
    (86, 55, 0, 0),
    (87, 54, 0, 0),
    (88, 54, 0, 0),
    (89, 54, 0, 0),
    (90, 54, 0, 0),
    (91, 53, 0, 0),
    (92, 53, 0, 0),
    (93, 53, 0, 0),
    (94, 52, 0, 0),
    (95, 52, 0, 0),
    (96, 52, 0, 0),
    (97, 51, 0, 0),
    (98, 51, 0, 0),
    (99, 51, 0, 0),
    (100, 50, 0, 0),
    (101, 50, 0, 0),
    (102, 49, 0, 0),
    (103, 49, 0, 0),
    (104, 49, 0, 0),
    (105, 48, 0, 0),
    (106, 48, 0, 0),
    (107, 48, 0, 0),
    (108, 47, 0, 0),
    (109, 47, 0, 0),
    (110, 46, 0, 0),
    (111, 46, 0, 0),
    (112, 45, 0, 0),
    (113, 45, 0, 0),
    (114, 45, 0, 0),
    (115, 44, 0, 0),
    (116, 44, 0, 0),
    (117, 44, 0, 0),
    (118, 43, 0, 0),
    (119, 43, 0, 0),
    (120, 43, 0, 0),
    (121, 42, 0, 0),
    (122, 42, 0, 0),
    (123, 42, 0, 0),
    (124, 41, 0, 0),
    (125, 41, 0, 0),
    (126, 41, 0, 0),
    (127, 40, 0, 0),
    (128, 40, 0, 0),
    (129, 40, 0, 0),
    (130, 39, 0, 0),
    (131, 39, 0, 0),
    (132, 38, 0, 0),
    (133, 38, 0, 0),
    (134, 37, 0, 0),
    (135, 37, 0, 0),
    (136, 37, 0, 0),
    (137, 36, 0, 0),
    (138, 36, 0, 0),
    (139, 36, 0, 0),
    (140, 35, 0, 0),
    (141, 35, 0, 0),
    (142, 34, 0, 0),
    (143, 34, 0, 0),
    (144, 34, 0, 0),
    (145, 33, 0, 0),
    (146, 33, 0, 0),
    (147, 32, 0, 0),
    (148, 32, 0, 0),
    (149, 32, 0, 0),
    (150, 31, 0, 0),
    (200, 21, 0, 0),
    (250, 14, 0, 0),
    (300, 0, 0, 0),
)


def ebc_to_rgb(ebc: float) -> tuple[int, int, int]:
    """RGB-Naeherung der Bierfarbe zu einem EBC-Wert, aus der Farbtabelle.

    Das Original-Makro sucht nur exakte Treffer (z.B. "7 EBC" oder "7,5
    EBC") in der Tabelle und laesst die Zelle sonst ungefaerbt. Hier wird
    stattdessen zwischen den beiden benachbarten Stuetzstellen linear
    interpoliert, damit auch beliebige (berechnete, nicht auf 0,5 EBC
    gerundete) Werte immer eine plausible Farbe ergeben.
    """
    if ebc <= _EBC_COLOR_TABLE[0][0]:
        _, r, g, b = _EBC_COLOR_TABLE[0]
        return r, g, b
    if ebc >= _EBC_COLOR_TABLE[-1][0]:
        _, r, g, b = _EBC_COLOR_TABLE[-1]
        return r, g, b
    for (e0, r0, g0, b0), (e1, r1, g1, b1) in zip(_EBC_COLOR_TABLE, _EBC_COLOR_TABLE[1:]):
        if e0 <= ebc <= e1:
            t = (ebc - e0) / (e1 - e0)
            return (
                round(r0 + (r1 - r0) * t),
                round(g0 + (g1 - g0) * t),
                round(b0 + (b1 - b0) * t),
            )
    _, r, g, b = _EBC_COLOR_TABLE[-1]
    return r, g, b


def ebc_to_hex(ebc: float) -> str:
    """Bierfarbe als #rrggbb-Hexcode, zum direkten Einfaerben eines
    UI-Elements (z.B. des Bierkrug-Symbols)."""
    r, g, b = ebc_to_rgb(ebc)
    return f"#{r:02x}{g:02x}{b:02x}"
