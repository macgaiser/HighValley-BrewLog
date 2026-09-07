import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.database import get_session
from app.inventory import restock
from app.models import InventoryCategory, InventoryItem
from app.templating import templates

router = APIRouter(prefix="/inventory", tags=["inventory"])


_FIXED_UNITS = {InventoryCategory.malz: "kg", InventoryCategory.hopfen: "g"}


def _resolve_unit(category: InventoryCategory, form_unit: str) -> str:
    """Malz und Hopfen gehen fest in kg bzw. g in die EBC-/IBU-Berechnung
    und die automatische Lagerabbuchung ein (ohne jede Umrechnung) - die
    Einheit ist dafuer nicht frei waehlbar, sondern liegt fest. Nur bei
    Hefe bleibt sie frei editierbar (z.B. fuer ml bei Fluessighefe)."""
    fixed = _FIXED_UNITS.get(category)
    if fixed:
        return fixed
    return form_unit.strip() or "kg"


def _parse_ebc(raw: str) -> float | None:
    """Parst eine EBC-Eingabe: eine einzelne Zahl ('4', '4,5') oder einen auf
    Malz-Datenblättern üblichen Bereich ('4-6') - dann wird der Mittelwert
    verwendet, statt einen Fehler zu werfen."""
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    parts = [p for p in re.split(r"\s*[-–—]\s*", raw) if p]
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    if not values:
        return None
    return round(sum(values) / len(values), 2)


@router.get("")
def inventory_list(request: Request, session: Session = Depends(get_session)):
    items = session.exec(select(InventoryItem)).all()
    grouped: dict[str, list[InventoryItem]] = {c.value: [] for c in InventoryCategory}
    for item in items:
        grouped[item.category.value].append(item)
    for group in grouped.values():
        group.sort(key=lambda i: i.amount, reverse=True)
    return templates.TemplateResponse(
        "inventory_list.html",
        {"request": request, "grouped": grouped, "categories": InventoryCategory},
    )


@router.get("/new")
def inventory_new_form(request: Request):
    return templates.TemplateResponse(
        "inventory_form.html", {"request": request, "item": None, "categories": InventoryCategory}
    )


@router.post("/new")
async def inventory_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    category = InventoryCategory(form.get("category"))
    item = InventoryItem(
        category=category,
        name=form.get("name", "").strip(),
        brand=form.get("brand", "").strip(),
        spec=form.get("spec", "").strip(),
        color_ebc=_parse_ebc(form.get("color_ebc", "")),
        unit=_resolve_unit(category, form.get("unit", "")),
        amount=0,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    initial_amount = float(form.get("initial_amount") or 0)
    if initial_amount > 0:
        restock(session, item, initial_amount, note="Anfangsbestand")
    return RedirectResponse("/inventory", status_code=303)


@router.get("/{item_id}/edit")
def inventory_edit_form(item_id: int, request: Request, session: Session = Depends(get_session)):
    item = session.get(InventoryItem, item_id)
    return templates.TemplateResponse(
        "inventory_form.html", {"request": request, "item": item, "categories": InventoryCategory}
    )


@router.post("/{item_id}/edit")
async def inventory_update(item_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    item = session.get(InventoryItem, item_id)
    item.category = InventoryCategory(form.get("category"))
    item.name = form.get("name", "").strip()
    item.brand = form.get("brand", "").strip()
    item.spec = form.get("spec", "").strip()
    item.color_ebc = _parse_ebc(form.get("color_ebc", ""))
    item.unit = _resolve_unit(item.category, form.get("unit", ""))
    session.add(item)
    session.commit()
    return RedirectResponse("/inventory", status_code=303)


@router.post("/{item_id}/restock")
async def inventory_restock(item_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    item = session.get(InventoryItem, item_id)
    amount = float(form.get("amount") or 0)
    note = form.get("note", "").strip()
    if item and amount != 0:
        if amount > 0:
            restock(session, item, amount, note=note or "Zubuchung")
        else:
            item.amount += amount
            session.add(item)
            from app.models import InventoryTransaction

            session.add(InventoryTransaction(item_id=item.id, delta=amount, note=note or "Korrektur"))
            session.commit()
    return RedirectResponse("/inventory", status_code=303)


@router.post("/{item_id}/delete")
def inventory_delete(item_id: int, session: Session = Depends(get_session)):
    item = session.get(InventoryItem, item_id)
    if item:
        session.delete(item)
        session.commit()
    return RedirectResponse("/inventory", status_code=303)


@router.get("/{item_id}")
def inventory_detail(item_id: int, request: Request, session: Session = Depends(get_session)):
    item = session.get(InventoryItem, item_id)
    transactions = sorted(item.transactions, key=lambda t: t.created_at, reverse=True)
    return templates.TemplateResponse(
        "inventory_detail.html", {"request": request, "item": item, "transactions": transactions}
    )
