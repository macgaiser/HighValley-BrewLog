import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.database import BORDER_GRAPHIC_DIR, LOGO_DIR, get_session
from app.models import BeerStyle, BorderGraphic, DefaultBrewDayTask, Logo, Settings
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ALLOWED_BORDER_GRAPHIC_EXT = ALLOWED_LOGO_EXT


def _f(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value.replace(",", "."))


@router.get("")
def settings_form(request: Request, session: Session = Depends(get_session)):
    s = session.get(Settings, 1)
    default_tasks = session.exec(select(DefaultBrewDayTask).order_by(DefaultBrewDayTask.position)).all()
    logos = session.exec(select(Logo).order_by(Logo.uploaded_at.desc())).all()
    beer_styles = session.exec(select(BeerStyle).order_by(BeerStyle.position)).all()
    border_graphics = session.exec(select(BorderGraphic).order_by(BorderGraphic.uploaded_at.desc())).all()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "s": s,
            "default_tasks": default_tasks,
            "logos": logos,
            "beer_styles": beer_styles,
            "border_graphics": border_graphics,
        },
    )


@router.post("")
async def settings_save(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    s = session.get(Settings, 1)
    s.malt_cost_per_kg = float(form.get("malt_cost_per_kg") or 0)
    s.hop_cost_per_100g = float(form.get("hop_cost_per_100g") or 0)
    s.yeast_flat_cost = float(form.get("yeast_flat_cost") or 0)
    s.labor_cost_per_hour = float(form.get("labor_cost_per_hour") or 0)
    s.wort_correction_factor = float(form.get("wort_correction_factor") or 1.03)
    s.mash_efficiency_correction_factor = float(form.get("mash_efficiency_correction_factor") or 100) / 100
    s.label_brand_name = form.get("label_brand_name", "").strip() or "HIGH VALLEY Brew Co."
    s.label_brand_line1 = form.get("label_brand_line1", "").strip()
    s.label_brand_line1_size = float(form.get("label_brand_line1_size") or 0.7)
    s.label_brand_line2_size = float(form.get("label_brand_line2_size") or 1.6)
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/beer-styles")
async def settings_beer_styles_save(request: Request, session: Session = Depends(get_session)):
    form = await request.form()

    for existing in session.exec(select(BeerStyle)).all():
        session.delete(existing)
    session.flush()

    names = form.getlist("style_name")
    position = 0
    for name in names:
        if not name.strip():
            continue
        session.add(BeerStyle(position=position, name=name.strip()))
        position += 1

    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/logos")
async def settings_logo_upload(session: Session = Depends(get_session), file: UploadFile = File(...)):
    """Neues Logo hochladen - wird auf Platte unter DATA_DIR/logos abgelegt
    (persistiert ueber das Docker-Volume) und direkt als aktives Logo fuer
    den Etikettengenerator gesetzt. Bereits hochgeladene Logos bleiben in
    der Galerie und koennen jederzeit wieder aktiviert werden."""
    if not file.filename:
        return RedirectResponse("/settings", status_code=303)
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_LOGO_EXT:
        ext = ".png"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    data = await file.read()
    (LOGO_DIR / stored_name).write_bytes(data)

    logo = Logo(filename=stored_name, original_filename=file.filename)
    session.add(logo)
    session.flush()
    s = session.get(Settings, 1)
    s.active_logo_id = logo.id
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/logos/{logo_id}/activate")
def settings_logo_activate(logo_id: int, session: Session = Depends(get_session)):
    logo = session.get(Logo, logo_id)
    if logo:
        s = session.get(Settings, 1)
        s.active_logo_id = logo.id
        session.add(s)
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/logos/{logo_id}/scale")
async def settings_logo_scale(logo_id: int, request: Request, session: Session = Depends(get_session)):
    """Fuellgrad eines einzelnen hochgeladenen Logos speichern - unabhaengig
    davon, ob es gerade aktiv ist, damit sich alle Logos schon vorab passend
    einstellen lassen."""
    form = await request.form()
    logo = session.get(Logo, logo_id)
    if logo:
        logo.scale_percent = float(form.get("scale_percent") or 82)
        session.add(logo)
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/logos/default-scale")
async def settings_default_logo_scale(request: Request, session: Session = Depends(get_session)):
    """Fuellgrad des eingebauten Standard-Logos speichern."""
    form = await request.form()
    s = session.get(Settings, 1)
    s.default_logo_scale = float(form.get("scale_percent") or 82)
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/logos/reset")
def settings_logo_reset(session: Session = Depends(get_session)):
    s = session.get(Settings, 1)
    s.active_logo_id = None
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/border-graphics")
async def settings_border_graphic_upload(session: Session = Depends(get_session), file: UploadFile = File(...)):
    """Neue Rahmengrafik hochladen (Ersatz fuer die frueher eingebaute,
    lizenzpflichtige Hopfenranke - die App liefert dafuer bewusst keine
    eigene Standardgrafik mehr mit). Wird auf Platte unter
    DATA_DIR/border_graphics abgelegt und direkt aktiv gesetzt. Skaliert
    sich auf dem Etikett automatisch ueber die volle Breite, Hoehe je nach
    Seitenverhaeltnis der Datei - am besten passt ein sehr breites,
    niedriges Bild (die eingebaute Hopfenranke war z.B. 583x86px, ca. 6.8:1)
    mit transparentem Hintergrund."""
    if not file.filename:
        return RedirectResponse("/settings", status_code=303)
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_BORDER_GRAPHIC_EXT:
        ext = ".png"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    data = await file.read()
    (BORDER_GRAPHIC_DIR / stored_name).write_bytes(data)

    graphic = BorderGraphic(filename=stored_name, original_filename=file.filename)
    session.add(graphic)
    session.flush()
    s = session.get(Settings, 1)
    s.active_border_graphic_id = graphic.id
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/border-graphics/{graphic_id}/activate")
def settings_border_graphic_activate(graphic_id: int, session: Session = Depends(get_session)):
    graphic = session.get(BorderGraphic, graphic_id)
    if graphic:
        s = session.get(Settings, 1)
        s.active_border_graphic_id = graphic.id
        session.add(s)
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/border-graphics/reset")
def settings_border_graphic_reset(session: Session = Depends(get_session)):
    s = session.get(Settings, 1)
    s.active_border_graphic_id = None
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/brew-day-tasks")
async def settings_brew_day_tasks_save(request: Request, session: Session = Depends(get_session)):
    form = await request.form()

    for existing in session.exec(select(DefaultBrewDayTask)).all():
        session.delete(existing)
    session.flush()

    task_names = form.getlist("task_name")
    task_durations = form.getlist("task_duration_min")
    task_notes = form.getlist("task_note")
    for i, name in enumerate(task_names):
        if not name.strip():
            continue
        session.add(
            DefaultBrewDayTask(
                position=i,
                task_name=name.strip(),
                planned_duration_min=_f(task_durations[i]) if i < len(task_durations) else None,
                note=task_notes[i].strip() if i < len(task_notes) else "",
            )
        )

    session.commit()
    return RedirectResponse("/settings", status_code=303)
