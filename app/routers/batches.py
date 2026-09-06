from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.batch_calc import compute_metrics, resolve_color_hex
from app.database import get_session
from app.inventory import sync_batch_deductions
from app.models import (
    Batch,
    BatchComment,
    BrewDayTask,
    CarbonationEntry,
    DefaultBrewDayTask,
    DryHopAddition,
    FermentationLogEntry,
    GrainAddition,
    HopAddition,
    HopAdditionType,
    InventoryCategory,
    InventoryItem,
    InventoryTransaction,
    Logo,
    MashStep,
    Settings,
    YeastAddition,
)
from app.templating import templates

router = APIRouter(prefix="/batches", tags=["batches"])

MASH_STEP_NAMES = [
    "Einmaischen",
    "1. Rast",
    "2. Rast",
    "3. Rast",
    "4. Rast",
    "5. Rast",
    "6. Rast",
    "Abmaischen",
]


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


def _resolve_ingredient_name(session: Session, manual_name: str, inventory_item_id: int | None) -> str:
    """Der Lagerartikel ist der Normalfall (Auswahl links) - ist einer
    ausgewaehlt, bestimmt dessen Name die Zutat, auch wenn im "Alternative"-
    Feld noch Text von einer frueheren Auswahl steht (sonst wuerde ein
    Wechsel des Lagerartikels ohne manuelles Leeren dieses Felds stillschweigend
    ignoriert). Die manuelle Eingabe zaehlt nur, wenn kein Lagerartikel
    ausgewaehlt ist - fuer Zutaten, die nicht im Lager sind."""
    if inventory_item_id:
        item = session.get(InventoryItem, inventory_item_id)
        if item:
            return item.name
    return manual_name.strip()


@router.get("")
def batch_list(
    request: Request,
    q: str = "",
    fermentation_type: str = "",
    ingredient_ids: list[int] = Query(default=[]),
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

    if ingredient_ids:
        wanted_ids = set(ingredient_ids)

        def used_ingredient_ids(b: Batch) -> set[int]:
            used: set[int] = set()
            for g in b.grain_additions:
                if g.inventory_item_id:
                    used.add(g.inventory_item_id)
            for h in b.hop_additions:
                if h.inventory_item_id:
                    used.add(h.inventory_item_id)
            for d in b.dry_hop_additions:
                if d.inventory_item_id:
                    used.add(d.inventory_item_id)
            for y in b.yeast_additions:
                if y.inventory_item_id:
                    used.add(y.inventory_item_id)
            return used

        # Kombination: der Sud muss ALLE ausgewählten Zutaten enthalten, nicht
        # nur irgendeine davon.
        batches = [b for b in batches if wanted_ids.issubset(used_ingredient_ids(b))]

    settings = session.get(Settings, 1)
    og_display: dict[int, float] = {}
    color_hex: dict[int, str] = {}
    for b in batches:
        if b.post_boil_brix:
            og_display[b.id] = round(b.post_boil_brix / settings.wort_correction_factor, 1)
        elif b.target_og_plato:
            og_display[b.id] = round(b.target_og_plato, 1)
        hex_value = resolve_color_hex(b)
        if hex_value:
            color_hex[b.id] = hex_value

    return templates.TemplateResponse(
        "batch_list.html",
        {
            "request": request,
            "batches": batches,
            "q": q,
            "fermentation_type": fermentation_type,
            "ingredient_ids": ingredient_ids,
            "inventory": _inventory_options(session),
            "og_display": og_display,
            "color_hex": color_hex,
        },
    )


@router.get("/new")
def batch_new_form(request: Request, session: Session = Depends(get_session)):
    next_number = (session.exec(select(Batch.batch_number).order_by(Batch.batch_number.desc())).first() or 0) + 1
    default_tasks = session.exec(select(DefaultBrewDayTask).order_by(DefaultBrewDayTask.position)).all()
    return templates.TemplateResponse(
        "batch_form.html",
        {
            "request": request,
            "batch": None,
            "next_number": next_number,
            "default_tasks": default_tasks,
            "mash_step_names": MASH_STEP_NAMES,
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
    batch.bottling_date = _d(form.get("bottling_date"))
    batch.inventory_deduction_locked = form.get("inventory_deduction_locked") == "on"
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

    # Maischplan-Kommentare werden in der Sud-Ansicht gepflegt (nicht hier im
    # Formular), muessen das Loeschen+Neuanlegen der Zeilen unten also
    # ueberleben - nur ueber die Position zuordenbar, da die Zeilen dabei
    # ihre ID verlieren.
    old_mash_comments = [s.comment for s in sorted(batch.mash_steps, key=lambda s: s.position)]

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
    session.flush()

    names = form.getlist("grain_malt_name")
    amounts = form.getlist("grain_amount_kg")
    inv_ids = form.getlist("grain_inventory_id")
    for i in range(len(names)):
        inv_id = int(inv_ids[i]) if i < len(inv_ids) and inv_ids[i] else None
        if not names[i].strip() and not inv_id:
            continue
        session.add(
            GrainAddition(
                batch_id=batch.id,
                position=i,
                malt_name=_resolve_ingredient_name(session, names[i], inv_id),
                amount_kg=_f(amounts[i]) or 0,
                inventory_item_id=inv_id,
            )
        )

    names = form.getlist("mash_name")
    temps = form.getlist("mash_temperature_c")
    durations = form.getlist("mash_duration_min")
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
                comment=old_mash_comments[i] if i < len(old_mash_comments) else "",
            )
        )

    names = form.getlist("hop_name")
    alphas = form.getlist("hop_alpha")
    hop_amounts = form.getlist("hop_amount_g")
    times = form.getlist("hop_time_min")
    hop_temps = form.getlist("hop_temperature_c")
    types = form.getlist("hop_type")
    hop_inv_ids = form.getlist("hop_inventory_id")
    for i in range(len(names)):
        hop_inv_id = int(hop_inv_ids[i]) if i < len(hop_inv_ids) and hop_inv_ids[i] else None
        if not names[i].strip() and not hop_inv_id:
            continue
        alpha = _f(alphas[i]) if i < len(alphas) else None
        session.add(
            HopAddition(
                batch_id=batch.id,
                position=i,
                hop_name=_resolve_ingredient_name(session, names[i], hop_inv_id),
                alpha_acid_percent=round(alpha, 1) if alpha is not None else None,
                amount_g=_f(hop_amounts[i]) or 0,
                time_min=_f(times[i]) if i < len(times) else None,
                temperature_c=_f(hop_temps[i]) if i < len(hop_temps) else None,
                addition_type=HopAdditionType(types[i]) if i < len(types) and types[i] else HopAdditionType.kochen,
                inventory_item_id=hop_inv_id,
            )
        )

    names = form.getlist("yeast_name")
    generations = form.getlist("yeast_generation")
    yeast_amounts = form.getlist("yeast_amount")
    yeast_units = form.getlist("yeast_unit")
    yeast_temps = form.getlist("yeast_temperature_c")
    yeast_comments = form.getlist("yeast_comment")
    yeast_inv_ids = form.getlist("yeast_inventory_id")
    for i in range(len(names)):
        yeast_inv_id = int(yeast_inv_ids[i]) if i < len(yeast_inv_ids) and yeast_inv_ids[i] else None
        if not names[i].strip() and not yeast_inv_id:
            continue
        session.add(
            YeastAddition(
                batch_id=batch.id,
                position=i,
                yeast_name=_resolve_ingredient_name(session, names[i], yeast_inv_id),
                generation_label=generations[i].strip() if i < len(generations) else "",
                amount=_f(yeast_amounts[i]) if i < len(yeast_amounts) else None,
                unit=yeast_units[i].strip() if i < len(yeast_units) and yeast_units[i] else "g",
                pitch_temperature_c=_f(yeast_temps[i]) if i < len(yeast_temps) else None,
                comment=yeast_comments[i].strip() if i < len(yeast_comments) else "",
                inventory_item_id=yeast_inv_id,
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


@router.get("/{batch_id}/label")
def batch_label(batch_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    settings = session.get(Settings, 1)
    metrics = compute_metrics(batch, settings)

    # Reihenfolge nach eingesetzter Menge (meiste Menge zuerst) statt nach
    # Eingabereihenfolge - mehrere Gaben derselben Sorte (z.B. Kochen +
    # Whirlpool) werden dafür zu einer Gesamtmenge aufsummiert.
    hop_amounts: dict[str, float] = {}
    for h in batch.hop_additions:
        if h.hop_name:
            hop_amounts[h.hop_name] = hop_amounts.get(h.hop_name, 0) + (h.amount_g or 0)
    hop_names_sorted = sorted(hop_amounts, key=lambda name: hop_amounts[name], reverse=True)
    hop_names = ", ".join(hop_names_sorted) if hop_names_sorted else "–"

    # Schriftgroesse der Hopfenzeile nach Textlaenge gestuft, damit sowohl
    # ein einzelner Hopfen (grosse Schrift) als auch eine lange Liste (auf
    # zwei Zeilen, kleinere Schrift) noch in die reservierte Flaeche passt.
    if len(hop_names) <= 26:
        hop_names_size = 1
    elif len(hop_names) <= 48:
        hop_names_size = 2
    elif len(hop_names) <= 75:
        hop_names_size = 3
    else:
        hop_names_size = 4

    logo_url = "/static/img/logo-shield.png"
    if settings.active_logo_id:
        logo = session.get(Logo, settings.active_logo_id)
        if logo:
            logo_url = f"/logos/{logo.filename}"
    return templates.TemplateResponse(
        "label.html",
        {
            "request": request,
            "batch": batch,
            "m": metrics,
            "hop_names": hop_names,
            "hop_names_size": hop_names_size,
            "label_count": range(9),
            "brand_name": settings.label_brand_name,
            "logo_url": logo_url,
        },
    )


@router.get("/{batch_id}/edit")
def batch_edit_form(batch_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    return templates.TemplateResponse(
        "batch_form.html",
        {
            "request": request,
            "batch": batch,
            "default_tasks": [],
            "mash_step_names": MASH_STEP_NAMES,
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


@router.post("/{batch_id}/copy")
def batch_copy(batch_id: int, session: Session = Depends(get_session)):
    source = session.get(Batch, batch_id)
    next_number = (session.exec(select(Batch.batch_number).order_by(Batch.batch_number.desc())).first() or 0) + 1

    copy = Batch(
        batch_number=next_number,
        name=source.name,
        style=source.style,
        fermentation_type=source.fermentation_type,
        target_volume_l=source.target_volume_l,
        color_ebc=source.color_ebc,
        main_water_l=source.main_water_l,
        sparge_water_l=source.sparge_water_l,
        lactic_acid_80_ml=source.lactic_acid_80_ml,
        boil_time_min=source.boil_time_min,
        target_og_plato=source.target_og_plato,
    )
    session.add(copy)
    session.commit()
    session.refresh(copy)

    for g in source.grain_additions:
        session.add(
            GrainAddition(
                batch_id=copy.id,
                position=g.position,
                malt_name=g.malt_name,
                amount_kg=g.amount_kg,
                inventory_item_id=g.inventory_item_id,
            )
        )
    for s in source.mash_steps:
        session.add(
            MashStep(
                batch_id=copy.id,
                position=s.position,
                name=s.name,
                temperature_c=s.temperature_c,
                duration_min=s.duration_min,
                comment=s.comment,
            )
        )
    for h in source.hop_additions:
        session.add(
            HopAddition(
                batch_id=copy.id,
                position=h.position,
                hop_name=h.hop_name,
                alpha_acid_percent=h.alpha_acid_percent,
                amount_g=h.amount_g,
                time_min=h.time_min,
                temperature_c=h.temperature_c,
                addition_type=h.addition_type,
                inventory_item_id=h.inventory_item_id,
            )
        )
    for y in source.yeast_additions:
        session.add(
            YeastAddition(
                batch_id=copy.id,
                position=y.position,
                yeast_name=y.yeast_name,
                generation_label=y.generation_label,
                amount=y.amount,
                unit=y.unit,
                pitch_temperature_c=y.pitch_temperature_c,
                comment=y.comment,
                inventory_item_id=y.inventory_item_id,
            )
        )
    for d in source.dry_hop_additions:
        session.add(
            DryHopAddition(
                batch_id=copy.id,
                position=d.position,
                hop_name=d.hop_name,
                timing_label=d.timing_label,
                amount_g=d.amount_g,
                inventory_item_id=d.inventory_item_id,
            )
        )
    for c in source.carbonation_entries:
        session.add(
            CarbonationEntry(
                batch_id=copy.id,
                position=c.position,
                sugar_g=c.sugar_g,
                bottle_volume_l=c.bottle_volume_l,
                label=c.label,
            )
        )
    # Zeitplan-Positionen werden übernommen, aber ohne Zeitwerte - die neuen
    # Zeiten hängen vom tatsächlichen Ablauf des neuen Brautags ab.
    for t in source.brew_day_tasks:
        session.add(
            BrewDayTask(
                batch_id=copy.id,
                position=t.position,
                task_name=t.task_name,
                planned_duration_min=None,
                note=t.note,
            )
        )
    # Gärverlauf und Kommentare sind sud-spezifisch und werden bewusst nicht
    # übernommen.

    session.commit()
    return RedirectResponse(f"/batches/{copy.id}/edit", status_code=303)


@router.get("/{batch_id}/mash/{step_id}/comment")
def mash_step_comment_form(batch_id: int, step_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    step = session.get(MashStep, step_id)
    return templates.TemplateResponse(
        "mash_comment_form.html",
        {"request": request, "batch": batch, "step": step},
    )


@router.post("/{batch_id}/mash/{step_id}/comment")
async def mash_step_comment_update(batch_id: int, step_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    step = session.get(MashStep, step_id)
    step.comment = form.get("comment", "").strip()
    session.add(step)
    session.commit()
    return RedirectResponse(f"/batches/{batch_id}", status_code=303)


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


@router.get("/{batch_id}/fermentation/{entry_id}/edit")
def fermentation_entry_edit_form(batch_id: int, entry_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    entry = session.get(FermentationLogEntry, entry_id)
    return templates.TemplateResponse(
        "fermentation_entry_form.html",
        {"request": request, "batch": batch, "entry": entry, "today": date.today().isoformat()},
    )


@router.post("/{batch_id}/fermentation/{entry_id}/edit")
async def fermentation_entry_update(batch_id: int, entry_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    entry = session.get(FermentationLogEntry, entry_id)
    entry.entry_date = _d(form.get("entry_date")) or date.today()
    entry.brix = _f(form.get("brix"))
    entry.comment = form.get("comment", "").strip()
    session.add(entry)
    session.commit()
    return RedirectResponse(f"/batches/{batch_id}", status_code=303)


@router.post("/{batch_id}/comments")
async def add_comment(batch_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    batch = session.get(Batch, batch_id)
    text = form.get("text", "").strip()
    if text:
        position = len(batch.comments)
        session.add(
            BatchComment(
                batch_id=batch_id,
                position=position,
                entry_date=_d(form.get("entry_date")) or date.today(),
                text=text,
            )
        )
        session.commit()
    return RedirectResponse(f"/batches/{batch_id}", status_code=303)


@router.get("/{batch_id}/comments/{comment_id}/edit")
def comment_edit_form(batch_id: int, comment_id: int, request: Request, session: Session = Depends(get_session)):
    batch = session.get(Batch, batch_id)
    comment = session.get(BatchComment, comment_id)
    return templates.TemplateResponse(
        "comment_form.html",
        {"request": request, "batch": batch, "comment": comment, "today": date.today().isoformat()},
    )


@router.post("/{batch_id}/comments/{comment_id}/edit")
async def comment_update(batch_id: int, comment_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    comment = session.get(BatchComment, comment_id)
    comment.entry_date = _d(form.get("entry_date")) or date.today()
    comment.text = form.get("text", "").strip()
    session.add(comment)
    session.commit()
    return RedirectResponse(f"/batches/{batch_id}", status_code=303)
