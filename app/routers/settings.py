from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.models import Settings
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def settings_form(request: Request, session: Session = Depends(get_session)):
    s = session.get(Settings, 1)
    return templates.TemplateResponse("settings.html", {"request": request, "s": s})


@router.post("")
async def settings_save(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    s = session.get(Settings, 1)
    s.malt_cost_per_kg = float(form.get("malt_cost_per_kg") or 0)
    s.hop_cost_per_100g = float(form.get("hop_cost_per_100g") or 0)
    s.yeast_flat_cost = float(form.get("yeast_flat_cost") or 0)
    s.labor_cost_per_hour = float(form.get("labor_cost_per_hour") or 0)
    s.wort_correction_factor = float(form.get("wort_correction_factor") or 1.03)
    s.mash_extract_potential = float(form.get("mash_extract_potential") or 80) / 100
    session.add(s)
    session.commit()
    return RedirectResponse("/settings", status_code=303)
