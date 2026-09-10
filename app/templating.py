import os

from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.database import engine
from app.models import BackgroundImage, Settings

templates = Jinja2Templates(directory="app/templates")

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _static_version(filename: str) -> str:
    """Cache-Busting fuer /static/style.css und /static/app.js: haengt die
    Aenderungszeit der Datei als Query-Parameter an, damit Browser nach
    jedem Deploy garantiert die neue Version laden statt (wie zuvor
    beobachtet) auf der alten CSS/JS unter derselben URL sitzen zu bleiben,
    waehrend die serverseitig gerenderten HTML-Seiten schon aktuell sind."""
    try:
        mtime = int(os.path.getmtime(os.path.join(_STATIC_DIR, filename)))
    except OSError:
        return ""
    return f"?v={mtime}"


templates.env.globals["static_version"] = _static_version


def _background_image_url() -> str:
    """Aktives Hintergrundbild ("Tal") - dieselbe Datei fuer den App-weiten
    Hintergrund (body::before, jede Seite) und das Marken-Feld auf dem
    Etikett (.label-brand::before), siehe --bg-valley-url in base.html/
    style.css. Anders als bei Logo/Rahmengrafik wird hier direkt in
    base.html aufgerufen (nicht ueber den jeweiligen Router durchgereicht),
    weil der App-Hintergrund auf jeder Seite gebraucht wird, nicht nur auf
    dem Etikett - eine eigene, kurze DB-Abfrage ist dafuer einfacher als das
    Settings-Objekt durch jede einzelne Route zu schleifen. Faellt ohne
    eigenen Upload auf das eingebaute bg-valley.png zurueck."""
    default_url = "/static/img/bg-valley.png"
    with Session(engine) as session:
        s = session.get(Settings, 1)
        if s and s.active_background_image_id:
            img = session.get(BackgroundImage, s.active_background_image_id)
            if img:
                return f"/background-images/{img.filename}"
    return default_url


templates.env.globals["background_image_url"] = _background_image_url


def _fmt(value, decimals: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value:.{decimals}f}"


def _de_date(value) -> str:
    if value is None:
        return "–"
    return value.strftime("%d.%m.%Y")


templates.env.filters["fmt"] = _fmt
templates.env.filters["de_date"] = _de_date
