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
aufrufen - Sude mit exakt gleichem Tab-Namen in beiden Dateien werden dabei
nur einmal importiert.

Das Braubuch-Layout hat sich über die Jahre mehrfach verändert (frühe Sude
sind knapper dokumentiert: keine Alphasäure je Hopfengabe, kein
strukturierter Gärverlauf, IBU/Ausbeute/Alkohol nur als von Hand
geschätzter Gesamtwert). Das Skript erkennt das jeweilige Layout pro
Tabellenblatt automatisch. Für Sude, bei denen die nötigen Rohdaten fehlen,
bleiben die entsprechenden berechneten Kennzahlen in der App leer (`–`)
statt einen falschen Wert vorzutäuschen; die damals von Hand eingetragene
Schätzung wird stattdessen als Kommentar "Original-Aufzeichnung im
Braubuch: ..." am Sud übernommen.

Getestet mit beiden Braubuch-Dateien (Sude #1-#48 aus dem älteren Archiv,
#49-#57 aus dem aktuellen Protokoll, insgesamt 58 Sude sowie 52
Lagerartikel).

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

`docker-compose.yml` nutzt standardmäßig ein fertiges Image von GitHub
(`ghcr.io/macgaiser/highvalley-brewlog:latest`) statt lokal aus dem Code zu
bauen. Auf der NAS wird also nur die `docker-compose.yml` (und `.env`)
benötigt, kein vollständiges Repository.

1. Nur die Datei `docker-compose.yml` (z.B. per File Station) in einen
   eigenen Ordner auf die NAS legen, z.B. `/docker/highvalley-brewlog/`
2. `.env.example` aus dem Repository herunterladen, nach `.env` umbenennen,
   Zugangsdaten anpassen und in denselben Ordner legen (oder die Werte
   direkt in `docker-compose.yml` eintragen)
3. In diesem Ordner:
   ```bash
   docker compose pull
   docker compose up -d
   ```
   Alternativ über die Synology **Container Manager**-Oberfläche: Projekt
   anlegen und den `docker-compose.yml`-Inhalt einfügen.
4. Die App ist danach unter `http://<NAS-IP>:5050` erreichbar (Port ist in
   `docker-compose.yml` frei anpassbar).

### Automatische Updates bei neuem Code

`docker-compose.yml` startet neben der App auch **Watchtower**, das alle 5
Minuten prüft, ob auf GitHub ein neueres Image liegt, und den Container bei
Bedarf automatisch neu zieht und neu startet - danach ist auf der NAS
nichts weiter zu tun.

Der Ablauf dahinter:
1. Ein Pull Request wird nach `main` gemergt.
2. GitHub Actions (`.github/workflows/docker-publish.yml`) baut daraufhin
   automatisch ein neues Container-Image und lädt es zu **GitHub Container
   Registry** (ghcr.io) hoch.
3. Watchtower auf der NAS bemerkt das neue Image (spätestens nach 5
   Minuten) und aktualisiert den `highvalley-brewlog`-Container
   automatisch. Die Datenbank in `./data` bleibt dabei unangetastet.

**Einmalige Einrichtung, damit die NAS das Image ohne Zugangsdaten laden
kann:** Nach dem ersten erfolgreichen GitHub-Actions-Lauf unter
`github.com/macgaiser/HighValley-BrewLog` → Reiter **"Packages"** →
`highvalley-brewlog` öffnen → **Package settings** → **Change visibility**
→ **Public**. Das Image enthält nur den App-Code, keine Braudaten (die
liegen ausschließlich in `./data` auf der NAS) - "public" ist hier also
unbedenklich. Ohne diesen Schritt bräuchte Watchtower zusätzlich ein
GitHub-Zugangstoken, um das (dann private) Image herunterzuladen.

Falls du stattdessen direkt aus dem Code bauen willst (z.B. für eigene,
noch nicht gemergte Änderungen): `docker-compose.yml` um `build: .`
ergänzen und mit `docker compose up -d --build` statt `pull` starten.

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
