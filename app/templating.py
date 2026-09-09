import os

from fastapi.templating import Jinja2Templates

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
