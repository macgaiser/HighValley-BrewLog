from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models import DefaultBrewDayTask, Settings
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])


def _f(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value.replace(",", "."))


@router.get("")
def settings_form(request: Request, session: Session = Depends(get_session)):
    s = session.get(Settings, 1)
    default_tasks = session.exec(select(DefaultBrewDayTask).order_by(DefaultBrewDayTask.position)).all()
    return templates.TemplateResponse(
        "settings.html", {"request": request, "s": s, "default_tasks": default_tasks}
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
