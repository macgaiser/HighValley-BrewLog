"""Lagerbestand-Logik: manuelles Zubuchen (Einkauf) und automatische
Abbuchung anhand der in einem Sud verwendeten Zutaten.

Die Abbuchung ist idempotent: beim Speichern eines Sud werden zunächst alle
bisherigen Buchungen dieses Suds rückgängig gemacht (Bestand wird
zurückgebucht) und dann anhand des aktuellen Zutatenstands neu gebucht. So
bleibt der Bestand auch bei mehrfachem Bearbeiten eines Suds korrekt.

Ist `Batch.inventory_deduction_locked` gesetzt, wird nach dem Zurückbuchen
bestehender Buchungen keine neue Abbuchung mehr vorgenommen - gedacht für
historische Sude, deren Zutaten längst real verbraucht wurden und die man
gefahrlos nachträglich bearbeiten (z.B. mit dem Lagerbestand verknüpfen)
können soll, ohne den aktuellen Bestand rückwirkend zu verändern.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.models import Batch, InventoryItem, InventoryTransaction


def restock(session: Session, item: InventoryItem, amount: float, note: str = "") -> InventoryTransaction:
    if amount <= 0:
        raise ValueError("Zubuchungsmenge muss größer als 0 sein")
    item.amount += amount
    item.updated_at = datetime.utcnow()
    session.add(item)
    tx = InventoryTransaction(item_id=item.id, delta=amount, note=note or "Zubuchung")
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


def sync_batch_deductions(session: Session, batch: Batch) -> None:
    existing = session.exec(
        select(InventoryTransaction).where(InventoryTransaction.batch_id == batch.id)
    ).all()
    for tx in existing:
        item = session.get(InventoryItem, tx.item_id)
        if item:
            item.amount -= tx.delta
            session.add(item)
        session.delete(tx)
    session.flush()

    # Für gesperrte Sude (z.B. historische/bereits abgeschlossene Importe)
    # werden bestehende Buchungen zwar oben zurückgebucht (falls vorhanden -
    # etwa wenn ein Sud nachträglich gesperrt wird), es entstehen aber keine
    # neuen. Der Bestand bleibt dadurch unangetastet, ganz gleich wie oft
    # dieser Sud gespeichert wird.
    if batch.inventory_deduction_locked:
        session.commit()
        return

    consumption: dict[int, float] = {}

    def add(item_id: int | None, amount: float | None) -> None:
        if item_id and amount:
            consumption[item_id] = consumption.get(item_id, 0) + amount

    for g in batch.grain_additions:
        add(g.inventory_item_id, g.amount_kg)
    for h in batch.hop_additions:
        add(h.inventory_item_id, h.amount_g)
    for d in batch.dry_hop_additions:
        add(d.inventory_item_id, d.amount_g)
    for y in batch.yeast_additions:
        add(y.inventory_item_id, y.amount)

    for item_id, amount in consumption.items():
        item = session.get(InventoryItem, item_id)
        if not item:
            continue
        item.amount -= amount
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.add(
            InventoryTransaction(
                item_id=item_id,
                batch_id=batch.id,
                delta=-amount,
                note=f"Verbrauch Sud #{batch.batch_number}",
            )
        )
    session.commit()
