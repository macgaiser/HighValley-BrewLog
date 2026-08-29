# HighValley BrewLog

Web-App für das Brauprotokoll (ehemals Excel), Lagerbestandsverwaltung
(Malz/Hopfen/Hefe) und Rezeptkennzahlen. Läuft als Docker-Container, z.B.
auf einer Synology NAS, und ist von jedem Gerät im Netzwerk per Browser
erreichbar.

## Funktionen

- **Sude verwalten**: Stammdaten, Wasser, Schüttung, Maischplan,
  Würzekochen/Hopfengaben, Hefegabe, Stopfhopfen, Karbonisierung,
  Gärverlauf, Brautag-Zeitplan und Kommentare – ein Sud pro Datensatz statt
  ein Excel-Tab pro Sud.
- **Automatisch berechnete Kennzahlen**: Bittere (IBU, Tinseth-Formel),
  Alkoholgehalt und Vergärungsgrad (Refraktometer-Korrektur nach Sean
  Terrill), Sudhausausbeute, Materialkosten je Sud und je 0,5-l-Flasche.
  Diese Formeln sind fachlich korrigierte Standardformeln aus der
  Brauliteratur – die ursprüngliche Excel-Vorlage enthielt u.a. eine
  Alkohol-Formel, die nie funktioniert hat (`#NAME?` in jedem Sud), siehe
  `app/formulas.py` für Quellenangaben.
- **Lagerbestand** für Malz, Hopfen und Hefe: Übersicht je Kategorie,
  manuelles Zubuchen (Einkauf) bzw. Korrekturen, und **automatische
  Abbuchung** anhand der in einem Sud verwendeten Zutaten (sofern eine
  Zutatzeile im Sud-Formular mit einem Lagerartikel verknüpft ist).
- **Einstellungen**: Durchschnittskosten für Malz/Hopfen/Hefe, Lohnkosten,
  Refraktometer-Korrekturfaktor und die für die Sudhausausbeute angenommene
  Malz-Extraktausbeute.
- Zugriffsschutz per HTTP Basic Auth (Benutzername/Passwort über
  Umgebungsvariablen).
- Persistenz in einer SQLite-Datenbank unter `/data` (Docker-Volume).

## Import der bisherigen Excel-Protokolle

`scripts/import_xlsx.py` liest die historischen Sude direkt aus der
Excel-Datei ein (ein Tab pro Sud, plus einen "Lagerbestand"-Tab) und legt
sie in der Datenbank an. Es werden **nur Werte übernommen, keine Formeln**
– alle Kennzahlen werden von der App selbst neu berechnet.

```bash
export DATA_DIR=./data   # oder der Pfad, den auch die App nutzt
python scripts/import_xlsx.py /pfad/zur/Brauprotokoll.xlsx
```

Der Import ist idempotent je Excel-Tab (ein bereits importierter Tab wird
beim erneuten Aufruf übersprungen) und der Lagerbestand wird nur beim
allerersten Import befüllt, um spätere manuelle Buchungen nicht zu
überschreiben. Bei mehreren Excel-Dateien (z.B. eine ältere Version mit
weiteren historischen Suden) einfach das Skript für jede Datei erneut
aufrufen.

## Lokale Entwicklung

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=./data
python run.py
```

Die Oberfläche ist danach unter `http://localhost:5000` erreichbar
(Standard-Login: `admin` / `brewlog`, unbedingt über Umgebungsvariablen
ändern).

## Deployment auf der Synology NAS (Docker / Container Manager)

1. Repository auf die NAS kopieren oder per Git clonen (z.B. via SSH oder
   File Station)
2. `.env.example` nach `.env` kopieren und Zugangsdaten anpassen, oder die
   Werte direkt in `docker-compose.yml` eintragen
3. Im Verzeichnis mit `docker-compose.yml`:
   ```bash
   docker compose up -d --build
   ```
   Alternativ über die Synology **Container Manager**-Oberfläche: Projekt
   anlegen und den `docker-compose.yml`-Inhalt einfügen.
4. Die App ist danach unter `http://<NAS-IP>:5050` erreichbar (Port ist in
   `docker-compose.yml` frei anpassbar).

**Historische Daten importieren** (einmalig, nach dem ersten Start):
```bash
docker compose exec brewlog python scripts/import_xlsx.py /data/Brauprotokoll.xlsx
```
Dazu die Excel-Datei vorher in den gemounteten `./data`-Ordner legen (dort
liegt sie dann unter `/data/...` im Container).

**Persistenz:** Der Ordner `./data` (gemountet nach `/data`) enthält die
komplette SQLite-Datenbank. Diesen Ordner bei Backups berücksichtigen.

**Sicherheit:** Die Oberfläche ist nur per HTTP Basic Auth geschützt.
Unbedingt `APP_USERNAME`/`APP_PASSWORD` auf sichere Werte setzen. Für einen
Zugriff aus dem Internet (nicht empfohlen) sollte zusätzlich eine
Reverse-Proxy-Konfiguration mit HTTPS (z.B. über die Synology-eigene
Reverse-Proxy-Funktion) und idealerweise VPN-Zugriff verwendet werden.

## Projektstruktur

```
app/
  models.py         SQLModel-Datenmodell (Sude, Zutaten, Lagerbestand)
  formulas.py        Brautechnische Berechnungen (IBU, ABV, Ausbeute, ...)
  batch_calc.py       Verknüpft Modell + Formeln zu Sud-Kennzahlen
  inventory.py         Zu-/Abbuchungslogik für den Lagerbestand
  routers/              FastAPI-Routen (Sude, Lagerbestand, Einstellungen)
  templates/             Jinja2-Templates
  static/                  CSS/JS
scripts/import_xlsx.py    Einmalig: Import der historischen Excel-Sude
```

## API-Übersicht (server-gerenderte Seiten, kein separates JSON-API)

Alle Routen (außer `/healthz`) erfordern HTTP Basic Auth.

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/batches` | Sud-Übersicht |
| GET/POST | `/batches/new` | Neuen Sud anlegen |
| GET | `/batches/{id}` | Sud-Detailansicht mit berechneten Kennzahlen |
| GET/POST | `/batches/{id}/edit` | Sud bearbeiten |
| POST | `/batches/{id}/delete` | Sud löschen (bucht Lagerbestand zurück) |
| POST | `/batches/{id}/fermentation` | Gärverlauf-Messung hinzufügen |
| GET | `/inventory` | Lagerbestand-Übersicht |
| GET/POST | `/inventory/new` | Neuen Lagerartikel anlegen |
| GET/POST | `/inventory/{id}/edit` | Lagerartikel bearbeiten |
| POST | `/inventory/{id}/restock` | Bestand zu-/abbuchen |
| GET/POST | `/settings` | Kosten- und Berechnungseinstellungen |
