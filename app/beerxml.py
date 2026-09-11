"""BeerXML-Export eines Suds (Rezept), zum Hochladen bei MySpeidel (Speidel
Braumeister) oder anderer Brausoftware.

MySpeidel akzeptiert Rezepte per Drag&Drop im BeerXML-Format - dieser Export
bildet Schüttung, Maischplan, Hopfengaben (inkl. Stopfhopfen) und Hefegabe
eines Suds als Standard-BeerXML-1.0-Datei ab.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from app.batch_calc import BatchMetrics
from app.models import Batch, HopAdditionType, Settings

_HOP_USE = {
    HopAdditionType.kochen: "Boil",
    HopAdditionType.whirlpool: "Aroma",
    HopAdditionType.nachisomerisierung: "Aroma",
}


def _sub(parent: ET.Element, tag: str, value) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def _ebc_to_srm(ebc: float) -> float:
    # BeerXML erwartet Malz-/Bierfarbe in Lovibond/SRM statt EBC - die App
    # rechnet intern mit EBC (siehe formulas.beer_color_ebc: EBC = SRM *
    # 1.97), hier also der Rückweg als Näherung.
    return round(ebc / 1.97, 1)


def build_recipe_xml(batch: Batch, settings: Settings, metrics: BatchMetrics) -> str:
    recipes = ET.Element("RECIPES")
    recipe = ET.SubElement(recipes, "RECIPE")

    _sub(recipe, "NAME", batch.name or f"Sud #{batch.batch_number}")
    _sub(recipe, "VERSION", 1)
    _sub(recipe, "TYPE", "All Grain")

    style = ET.SubElement(recipe, "STYLE")
    _sub(style, "NAME", batch.style or "")
    _sub(style, "VERSION", 1)
    _sub(style, "CATEGORY", "")
    _sub(style, "CATEGORY_NUMBER", "")
    _sub(style, "STYLE_LETTER", "")
    _sub(style, "STYLE_GUIDE", "")
    _sub(style, "TYPE", "Lager" if batch.fermentation_type == "Untergärig" else "Ale")
    _sub(style, "OG_MIN", 0)
    _sub(style, "OG_MAX", 0)
    _sub(style, "FG_MIN", 0)
    _sub(style, "FG_MAX", 0)
    _sub(style, "IBU_MIN", 0)
    _sub(style, "IBU_MAX", 0)
    _sub(style, "COLOR_MIN", 0)
    _sub(style, "COLOR_MAX", 0)

    _sub(recipe, "BREWER", settings.label_brand_name or "")
    _sub(recipe, "BATCH_SIZE", round(batch.target_volume_l or 0, 2))
    _sub(recipe, "BOIL_SIZE", round(batch.post_lauter_volume_l or batch.target_volume_l or 0, 2))
    _sub(recipe, "BOIL_TIME", batch.boil_time_min or 0)
    _sub(
        recipe,
        "EFFICIENCY",
        round(metrics.mash_efficiency_percent, 1) if metrics.mash_efficiency_percent else 70,
    )

    fermentables = ET.SubElement(recipe, "FERMENTABLES")
    for g in batch.grain_additions:
        if not g.malt_name:
            continue
        el = ET.SubElement(fermentables, "FERMENTABLE")
        _sub(el, "NAME", g.malt_name)
        _sub(el, "VERSION", 1)
        _sub(el, "AMOUNT", round(g.amount_kg or 0, 3))
        _sub(el, "TYPE", "Grain")
        _sub(el, "YIELD", 75)
        ebc = g.inventory_item.color_ebc if (g.inventory_item and g.inventory_item.color_ebc) else None
        _sub(el, "COLOR", _ebc_to_srm(ebc) if ebc else 0)

    hops = ET.SubElement(recipe, "HOPS")
    for h in batch.hop_additions:
        if not h.hop_name:
            continue
        el = ET.SubElement(hops, "HOP")
        _sub(el, "NAME", h.hop_name)
        _sub(el, "VERSION", 1)
        _sub(el, "ALPHA", round(h.alpha_acid_percent or 0, 1))
        _sub(el, "AMOUNT", round((h.amount_g or 0) / 1000, 4))
        _sub(el, "USE", _HOP_USE.get(h.addition_type, "Boil"))
        _sub(el, "TIME", round(h.time_min or 0, 1))
        _sub(el, "FORM", "Pellet")
    for dh in batch.dry_hop_additions:
        if not dh.hop_name:
            continue
        el = ET.SubElement(hops, "HOP")
        _sub(el, "NAME", dh.hop_name)
        _sub(el, "VERSION", 1)
        _sub(el, "ALPHA", 0)
        _sub(el, "AMOUNT", round((dh.amount_g or 0) / 1000, 4))
        _sub(el, "USE", "Dry Hop")
        _sub(el, "TIME", 0)
        _sub(el, "FORM", "Pellet")
        if dh.timing_label:
            _sub(el, "NOTES", dh.timing_label)

    yeasts = ET.SubElement(recipe, "YEASTS")
    for y in batch.yeast_additions:
        if not y.yeast_name:
            continue
        el = ET.SubElement(yeasts, "YEAST")
        _sub(el, "NAME", y.yeast_name)
        _sub(el, "VERSION", 1)
        _sub(el, "TYPE", "Lager" if batch.fermentation_type == "Untergärig" else "Ale")
        _sub(el, "FORM", "Dry")
        _sub(el, "AMOUNT", round(y.amount or 0, 3))
        _sub(el, "AMOUNT_IS_WEIGHT", "TRUE" if (y.unit or "").lower() in ("g", "kg") else "FALSE")
        notes = " ".join(x for x in [y.generation_label, y.comment] if x)
        if notes:
            _sub(el, "NOTES", notes)

    if batch.water_profile:
        wp = batch.water_profile
        waters = ET.SubElement(recipe, "WATERS")
        el = ET.SubElement(waters, "WATER")
        _sub(el, "NAME", wp.name)
        _sub(el, "VERSION", 1)
        _sub(el, "AMOUNT", round((batch.main_water_l or 0) + (batch.sparge_water_l or 0), 2))
        _sub(el, "CALCIUM", wp.calcium_ppm or 0)
        _sub(el, "BICARBONATE", wp.bicarbonate_ppm or 0)
        _sub(el, "SULFATE", wp.sulfate_ppm or 0)
        _sub(el, "CHLORIDE", wp.chloride_ppm or 0)
        _sub(el, "SODIUM", wp.sodium_ppm or 0)
        _sub(el, "MAGNESIUM", wp.magnesium_ppm or 0)
        if wp.ph:
            _sub(el, "PH", wp.ph)

    mash = ET.SubElement(recipe, "MASH")
    _sub(mash, "NAME", "Maischplan")
    _sub(mash, "VERSION", 1)
    _sub(mash, "GRAIN_TEMP", 20)
    mash_steps = ET.SubElement(mash, "MASH_STEPS")
    for step in batch.mash_steps:
        if not step.name:
            continue
        el = ET.SubElement(mash_steps, "MASH_STEP")
        _sub(el, "NAME", step.name)
        _sub(el, "VERSION", 1)
        _sub(el, "TYPE", "Temperature")
        _sub(el, "STEP_TEMP", step.temperature_c or 0)
        _sub(el, "STEP_TIME", step.duration_min or 0)

    _sub(recipe, "NOTES", f"Aus HighValley BrewLog: Sud #{batch.batch_number}")

    rough = ET.tostring(recipes, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    lines = [line for line in pretty.split("\n") if line.strip()]
    # minidom erzeugt eine eigene Deklaration ohne Encoding-Angabe - durch
    # eine mit "UTF-8" ersetzen, wie von BeerXML-Lesern erwartet.
    lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines)
