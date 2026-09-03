from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.batch_calc import compute_metrics
from app.database import get_session
from app.inventory import sync_batch_deductions
from app.models import (
    Batch,
    BatchComment,
    BrewDayTask,
    CarbonationEntry,
    DryHopAddition,
    FermentationLogEntry,
    GrainAddition,
    HopAddition,
    HopAdditionType,
    InventoryCategory,
    InventoryItem,
    InventoryTransaction,
    MashStep,
    Settings,
    YeastAddition,
)
from app.templating import templates

router = APIRouter(prefix="/batches", tags=["batches"])


def _f(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value.replace(",", "."))


def _d(value: str | None) -> date | None:
    if value is None or value.strip() == "":
        return None
    return date.fromisoformat(value)


def _inventory_options(session: Session) -> dict[str, list[InventoryItem]]:
    items = session.exec(select(InventoryItem).order_by(InventoryItem.name)).all()
    return {
        "malz": [i for i in items if i.category == InventoryCategory.malz],
        "hopfen": [i for i in items if i.category == InventoryCategory.hopfen],
        "hefe": [i for i in items if i.category == InventoryCategory.hefe],
    }


@router.get("")
def batch_list(
    request: Request,
    q: str = "",
    fermentation_type: str = "",
    session: Session = Depends(get_session),
):
    stmt = select(Batch).order_by(Batch.batch_number.desc())
    batches = session.exec(stmt).all()
    if fermentation_type:
        batches = [b for b in batches if b.fermentation_type == fermentation_type]
    if q:
        ql = q.lower()

        def matches(b: Batch) -> bool:
            if ql in str(b.batch_number) or ql in (b.name or "").lower() or ql in (b.style or "").lower():
                return True
            if any(ql in (g.malt_name or "").lower() for g in b.grain_additions):
                return True
            if any(ql in (h.hop_name or "").lower() for h in b.hop_additions):
                return True
            if any(ql in (d.hop_name or "").lower() for d in b.dry_hop_additions):
                return True
            if any(ql in (y.yeast_name or "").lower() for y in b.yeast_additions):
                return True
            return False

        batches = [b for b in batches if matches(b)]
    return templates.TemplateResponse(
        "batch_list.html",
        {"request": request, "batches": batches, "q": q, "fermentation_type": fermentation_type},
    )


@router.get("/new")
def batch_new_form(request: Request, session: Session = Depends(get_session)):
    next_number = (session.exec(select(Batch.batch_number).order_by(Batch.batch_number.desc())).first() or 0) + 1
    return templates.TemplateResponse(
        "batch_form.html",
        {
            "request": request,
            "batch": None,
            "next_number": next_number,
            "inventory": _inventory_options(session),
            "hop_types": list(HopAdditionType),
        },
    )


async def _apply_form_to_batch(batch: Batch, form, session: Session) -> None:
    batch.batch_number = int(form.get("batch_number"))
    batch.name = form.get("name", "").strip()
    batch.style = form.get("style", "").strip()
    batch.fermentation_type = form.get("fermentation_type", "").strip()
    batch.brew_date = _d(form.get("brew_date"))
    batch.target_volume_l = _f(form.get("target_volume_l"))
    batch.color_ebc = _f(form.get("color_ebc"))
    batch.main_water_l = _f(form.get("main_water_l"))
    batch.sparge_water_l = _f(form.get("sparge_water_l"))
    batch.lactic_acid_80_ml = _f(form.get("lactic_acid_80_ml"))
    batch.boil_time_min = _f(form.get("boil_time_min"))
    batch.target_og_plato = _f(form.get("target_og_plato"))
    batch.pre_lauter_brix = _f(form.get("pre_lauter_brix"))
    batch.post_lauter_brix = _f(form.get("post_lauter_brix"))
    batch.post_lauter_volume_l = _f(form.get("post_lauter_volume_l"))
    batch.water_adjustment_l = _f(form.get("water_adjustment_l"))
    batch.post_boil_brix = _f(form.get("post_boil_brix"))
    batch.post_boil_volume_l = _f(form.get("post_boil_volume_l"))
    batch.updated_at = datetime.utcnow()
    session.add(batch)
    session.commit()
    session.refresh(batch)

    # Bestehende Unterlisten ersetzen (einfacher & robuster als Diffs)
    for existing in list(batch.grain_additions):
        session.delete(existing)
    for existing in list(batch.mash_steps):
        session.delete(existing)
    for existing in list(batch.hop_additions):
        session.delete(existing)
    for existing in list(batch.yeast_additions):
        session.delete(existing)
    for existing in list(batch.dry_hop_additions):
        session.delete(existing)
    for existing in list(batch.carbonation_entries):
        session.delete(existing)
    for existing in list(batch.brew_day_tasks):
        session.delete(existing)
    for existing in list(batch.comments):
        session.delete(existing)
    session.flush()

    names = form.getlist("grain_malt_name")
    amounts = form.getlist("grain_amount_kg")
    inv_ids = form.getlist("grain_inventory_id")
    for i, name in enumerate(names):
        if not name.strip():
            continue
        session.add(
            GrainAddition(
                batch_id=batch.id,
                position=i,
                malt_name=name.strip(),
                amount_kg=_f(amounts[i]) or 0,
                inventory_item_id=int(inv_ids[i]) if i < len(inv_ids) and inv_ids[i] else None,
            )
        )

    names = form.getlist("mash_name")
    temps = form.getlist("mash_temperature_c")
    durations = form.getlist("mash_duration_min")
    comments = form.getlist("mash_comment")
    for i, name in enumerate(names):
        if not name.strip():
            continue
        session.add(
            MashStep(
                batch_id=batch.id,
                position=i,
                name=name.strip(),
                temperature_c=_f(temps[i]) if i < len(temps) else None,
                duration_min=_f(durations[i]) if i < len(durations) else None,
                comment=comments[i].strip() if i < len(comments) else "",
            )
        )

    names = form.getlist("hop_name")
    alphas = form.getlist("hop_alpha")
    hop_amounts = form.getlist("hop_amount_g")
    times = form.getlist("hop_time_min")
    hop_temps = form.getlist("hop_temperature_c")
    types = form.getlist("hop_type")
    hop_inv_ids = form.getlist("hop_inventory_id")
    for i, name in enumerate(names):
        if not name.strip():
            continue
        session.add(
            HopAddition(
                batch_id=batch.id,
                position=i,
                hop_name=name.strip(),
                alpha_acid_percent=_f(alphas[i]) if i < len(alphas) else None,
                amount_g=_f(hop_amounts[i]) or 0,
                time_min=_f(times[i]) if i < len(times) else None,
                temperature_c=_f(hop_temps[i]) if i < len(hop_temps) else None,
                addition_type=HopAdditionType(types[i]) if i < len(types) and types[i] else HopAdditionType.kochen,
                inventory_item_id=int(hop_inv_ids[i]) if i < len(hop_inv_ids) and hop_inv_ids[i] else None,
            )
        )

    names = form.getlist("yeast_name")
    generations = form.getlist("yeast_generation")
    yeast_amounts = form.getlist("yeast_amount")
    yeast_units = form.getlist("yeast_unit")
    yeast_temps = form.getlist("yeast_temperature_c")
    yeast_inv_ids = form.getlist("yeast_inventory_id")
    for i, name in enumerate(names):
        if not name.strip():
            continue
        session.add(
            YeastAddition(
                batch_id=batch.id,
                position=i,
                yeast_name=name.strip(),
                generation_label=generations[i].strip() if i < len(generations) else "",
                amount=_f(yeast_amounts[i]) if i < len(yeast_amounts) else None,
                unit=yeast_units[i].strip() if i < len(yeast_units) and yeast_units[i] else "g",
                pitch_temperature_c=_f(yeast_temps[i]) if i < len(yeast_temps) else None,
                inventory_item_id=int(yeast_inv_ids[i]) if i < len(yeast_inv_ids) and yeast_inv_ids[i] else None,
            )
        )

    names = form.getlist("dryhop_name")
    timings = form.getlist("dryhop_timing")
    dryhop_amounts = form.getlist("dryhop_amount_g")
    dryhop_inv_ids = form.getlist("dryhop_inventory_id")
    for i, name in enumerate(names):
        if not name.strip():
            continue
        session.add(
            DryHopAddition(
                batch_id=batch.id,
                position=i,
                hop_name=name.strip(),
                timing_label=timings[i].strip() if i < len(timings) else "",
                amount_g=_f(dryhop_amounts[i]) or 0,
                inventory_item_id=int(dryhop_inv_ids[i]) if i < len(dryhop_inv_ids) and dryhop_inv_ids[i] else None,
            )
        )

    sugars = form.getlist("carb_sugar_g")
    bottles = form.getlist("carb_bottle_l")
    for i, sugar in enumerate(sugars):
        if not sugar.strip():
            continue
        session.add(
            CarbonationEntry(
                batch_id=batch.id,
                position=i,
                sugar_g=_f(sugar) or 0,
                bottle_volume_l=_f(bottles[i]) or 0.5 if i < len(bottles) else 0.5,
            )
        )

    task_names = form.getlist("task_name")
    task_durations = form.getlist("task_duration_min")
    task_notes = form.getlist("task_note")
    for i, name in enumerate(task_names):
        if not name.strip():
            continue
        session.add(
            BrewDayTask(
                batch_id=batch.id,
                position=i,
                task_name=name.strip(),
                planned_duration_min=_f(task_durations[i]) if i < len(task_durations) else None,
                note=task_notes[i].strip() if i < len(task_notes) else "",
            )
        )

    comments_text = form.get("comments_text", "") or ""
    for i, line in enumerate(l for l in comments_text.splitlines() if l.strip()):
        session.add(BatchComment(batch_id=batch.id, position=i, text=line.strip()))

    session.commit()
    session.refresh(batch)
    sync_batch_deductions(session, batch)


@router.post("/new")
async def batch_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    batch = Batch(batch_number=int(form.get("batch_number")))
    await _apply_form_to_batch(batch, form, session)
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.get("/{batch_id}")
def batch_detail(batch_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    settings = session.get(Settings, 1)
    metrics = compute_metrics(batch, settings)
    return templates.TemplateResponse(
        "batch_detail.html",
        {"request": request, "batch": batch, "m": metrics, "today": date.today().isoformat()},
    )


@router.get("/{batch_id}/edit")
def batch_edit_form(batch_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    comments_text = "\n".join(c.text for c in batch.comments)
    return templates.TemplateResponse(
        "batch_form.html",
        {
            "request": request,
            "batch": batch,
            "comments_text": comments_text,
            "inventory": _inventory_options(session),
            "hop_types": list(HopAdditionType),
        },
    )


@router.post("/{batch_id}/edit")
async def batch_update(batch_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    form = await request.form()
    await _apply_form_to_batch(batch, form, session)
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/delete")
def batch_delete(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    if batch:
        for tx in session.exec(
            select(InventoryTransaction).where(InventoryTransaction.batch_id == batch_id)
        ).all():
            item = session.get(InventoryItem, tx.item_id)
            if item:
                item.amount -= tx.delta
                session.add(item)
            session.delete(tx)
        session.delete(batch)
        session.commit()
    return RedirectResponse("/batches", status_code=303)


@router.post("/{batch_id}/fermentation")
async def add_fermentation_entry(batch_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    batch = session.get(Batch, batch_id)
    position = len(batch.fermentation_entries)
    session.add(
        FermentationLogEntry(
            batch_id=batch_id,
            position=position,
            entry_date=_d(form.get("entry_date")) or date.today(),
            brix=_f(form.get("brix")),
            comment=form.get("comment", "").strip(),
        )
    )
    session.commit()
    return RedirectResponse(f"/batches/{batch_id}", status_code=303)
