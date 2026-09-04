"""Verknüpft nachträglich bestehende Zutat-Einträge (Schüttung, Hopfengaben,
Stopfhopfen, Hefegabe) mit einem passenden Lagerartikel, anhand des Namens.

Hintergrund: Der Zutaten-Filter in der Sudübersicht und die automatische
Lagerabbuchung funktionieren nur für Zutat-Zeilen, die im Sud-Formular über
das Dropdown mit einem konkreten Lagerartikel verknüpft sind (Feld
`inventory_item_id`). Der Excel-Import (`import_xlsx.py`) übernimmt nur den
Namen als Text, ohne diese Verknüpfung zu setzen - dadurch bleiben Filter
und automatische Abbuchung für alle importierten Sude wirkungslos, auch wenn
der Name exakt einem Lagerartikel entspricht.

Dieses Skript holt das nachträglich nach: für jede noch unverknüpfte
Zutat-Zeile wird per Namensvergleich (ohne Berücksichtigung von
Groß-/Kleinschreibung und Leerzeichen am Rand) innerhalb der passenden
Kategorie (Malz/Hopfen/Hefe) nach einem eindeutig passenden Lagerartikel
gesucht. Mehrdeutige oder nicht gefundene Namen werden übersprungen und am
Ende aufgelistet, damit sie bei Bedarf manuell verknüpft werden können.

Aufruf (zeigt nur eine Vorschau, ändert nichts):
    python scripts/link_inventory.py

Aufruf zum tatsächlichen Verknüpfen:
    python scripts/link_inventory.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.database import engine
from app.models import (
    DryHopAddition,
    GrainAddition,
    HopAddition,
    InventoryCategory,
    InventoryItem,
    YeastAddition,
)

# (Modell, Namensfeld, Lagerbestand-Kategorie)
TARGETS = [
    (GrainAddition, "malt_name", InventoryCategory.malz),
    (HopAddition, "hop_name", InventoryCategory.hopfen),
    (DryHopAddition, "hop_name", InventoryCategory.hopfen),
    (YeastAddition, "yeast_name", InventoryCategory.hefe),
]


def _norm(name: str) -> str:
    return (name or "").strip().casefold()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Änderungen tatsächlich speichern (sonst nur Vorschau)")
    args = parser.parse_args()

    with Session(engine) as session:
        linked = 0
        already_linked = 0
        no_match: dict[str, int] = defaultdict(int)
        ambiguous: dict[str, int] = defaultdict(int)

        for model, name_field, category in TARGETS:
            items = session.exec(select(InventoryItem).where(InventoryItem.category == category)).all()
            by_name: dict[str, list[InventoryItem]] = defaultdict(list)
            for item in items:
                by_name[_norm(item.name)].append(item)

            rows = session.exec(select(model)).all()
            for row in rows:
                if row.inventory_item_id:
                    already_linked += 1
                    continue
                raw_name = getattr(row, name_field)
                key = _norm(raw_name)
                if not key:
                    continue
                candidates = by_name.get(key, [])
                if len(candidates) == 1:
                    print(f"  {model.__name__}: '{raw_name}' -> Lagerartikel '{candidates[0].name}' (#{candidates[0].id})")
                    if args.apply:
                        row.inventory_item_id = candidates[0].id
                        session.add(row)
                    linked += 1
                elif len(candidates) > 1:
                    ambiguous[f"{model.__name__}: '{raw_name}'"] += 1
                else:
                    no_match[f"{model.__name__}: '{raw_name}'"] += 1

        if args.apply:
            session.commit()

        print()
        print(f"Bereits verknüpft: {already_linked}")
        print(f"{'Verknüpft' if args.apply else 'Würde verknüpft (Vorschau, --apply zum Ausführen)'}: {linked}")

        if ambiguous:
            print(f"\nMehrdeutig (mehrere Lagerartikel mit gleichem Namen), übersprungen:")
            for name, count in sorted(ambiguous.items()):
                print(f"  {name} ({count}x)")

        if no_match:
            print(f"\nKein passender Lagerartikel gefunden, übersprungen:")
            for name, count in sorted(no_match.items()):
                print(f"  {name} ({count}x)")


if __name__ == "__main__":
    main()
