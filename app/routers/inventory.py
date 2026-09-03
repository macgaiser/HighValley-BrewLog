from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.database import get_session
from app.inventory import restock
from app.models import InventoryCategory, InventoryItem
from app.templating import templates

router = APIRouter(prefix="/inventory", tags=["inventory"])


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
    item = InventoryItem(
        category=InventoryCategory(form.get("category")),
        name=form.get("name", "").strip(),
        brand=form.get("brand", "").strip(),
        spec=form.get("spec", "").strip(),
        unit=form.get("unit", "kg").strip() or "kg",
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
    item.unit = form.get("unit", "kg").strip() or "kg"
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
