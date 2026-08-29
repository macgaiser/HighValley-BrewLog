from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _fmt(value, decimals: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value:.{decimals}f}"


templates.env.filters["fmt"] = _fmt
