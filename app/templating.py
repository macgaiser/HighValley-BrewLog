from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


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
