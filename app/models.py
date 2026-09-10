"""SQLModel-Datenmodell für das Brauprotokoll.

Bildet die Struktur der ursprünglichen Excel-Vorlage ab (ein Tab pro Sud mit
Wasser, Schüttung, Maischplan, Würzekochen/Hopfengaben, Hefegabe,
Stopfhopfen, Karbonisierung, Gärverlauf, Kommentaren und einem
Brautag-Zeitplan) plus einer separaten Lagerbestandsverwaltung für Malz,
Hopfen und Hefe mit Buchungshistorie.
"""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class InventoryCategory(str, Enum):
    malz = "malz"
    hopfen = "hopfen"
    hefe = "hefe"


class HopAdditionType(str, Enum):
    kochen = "kochen"
    whirlpool = "whirlpool"
    nachisomerisierung = "nachisomerisierung"


class Settings(SQLModel, table=True):
    """Global einstellbare Standardwerte (Kosten, Annahmen), analog zum
    "Kosten:"-Block in der Excel-Vorlage. Es gibt genau eine Zeile (id=1)."""

    id: Optional[int] = Field(default=1, primary_key=True)
    malt_cost_per_kg: float = 2.8
    hop_cost_per_100g: float = 7.0
    yeast_flat_cost: float = 3.0
    labor_cost_per_hour: float = 30.0
    wort_correction_factor: float = 1.03
    mash_efficiency_correction_factor: float = 1.0
    label_brand_name: str = "HIGH VALLEY Brew Co."
    label_brand_line1: str = ""
    label_brand_line1_size: float = 0.7
    label_brand_line2_size: float = 1.6
    active_logo_id: Optional[int] = Field(default=None, foreign_key="logo.id")
    default_logo_scale: float = 82.0  # Fuellgrad des eingebauten Standard-Logos in % der Logo-Box
    active_border_graphic_id: Optional[int] = Field(default=None, foreign_key="bordergraphic.id")
    # Einzige Akzentfarbe des Etiketts (Rahmen, Schrift, Icon-Umrandungen -
    # alles, was aktuell gruen bzw. im Dunkelmodus gold ist), je Modus separat
    # einstellbar statt pro Element - steuert ueber --label-accent-light/-dark
    # (siehe label.html) die bestehende --label-green-Variable in style.css.
    label_accent_light: str = "#1a6b1a"
    label_accent_dark: str = "#f3c750"
    active_background_image_id: Optional[int] = Field(default=None, foreign_key="backgroundimage.id")


class Logo(SQLModel, table=True):
    """Ein hochgeladenes Logo-Bild fuer den Etikettengenerator. Bleibt nach
    dem Hochladen dauerhaft in der Galerie erhalten, auch wenn spaeter ein
    anderes Logo aktiv gesetzt wird - so kann jederzeit wieder zu einem
    frueher genutzten Logo zurueckgewechselt werden."""

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str  # Dateiname auf der Platte, unter DATA_DIR/logos
    original_filename: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    # Manuell einstellbarer Fuellgrad des Logos in der Logo-Box auf dem
    # Etikett (in %) - je nach Logo unterschiedlich sinnvoll (ein Logo mit
    # viel eigenem Weissraum braucht einen groesseren Wert als eines, das
    # bereits bis an den Rand geht).
    scale_percent: float = 82.0


class BorderGraphic(SQLModel, table=True):
    """Eine hochgeladene Rahmengrafik (z.B. Hopfenranke) fuer den oberen/
    unteren Rand des Etiketts. Anders als beim Logo gibt es keine
    eingebaute Standardgrafik - die App liefert dafuer keine mit aus
    (Lizenzgruende), das Feld bleibt leer, bis ein eigenes Bild hochgeladen
    wird. Skaliert sich automatisch: die Grafik wird ueber die volle
    Etikettenbreite gestreckt, die Hoehe ergibt sich aus ihrem eigenen
    Seitenverhaeltnis (siehe .label-vine-img in style.css)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str  # Dateiname auf der Platte, unter DATA_DIR/border_graphics
    original_filename: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class BackgroundImage(SQLModel, table=True):
    """Ein hochgeladenes Hintergrundbild ("Tal") - ersetzt das eingebaute
    bg-valley.png sowohl im App-Hintergrund (jede Seite) als auch im
    Marken-Feld des Etiketts (dieselbe Datei fuer beide, siehe
    background_image_url() in templating.py). Anders als bei der
    Rahmengrafik bleibt das eingebaute Bild hier als Standard erhalten -
    nur bei aktivem Wunsch nach einem eigenen wird es ersetzt."""

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str  # Dateiname auf der Platte, unter DATA_DIR/background_images
    original_filename: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class DefaultBrewDayTask(SQLModel, table=True):
    """Vorlage-Position für den Brautag-Zeitplan, die bei einem neuen Sud
    automatisch vorbelegt wird (editierbar unter Einstellungen)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    position: int = 0
    task_name: str
    planned_duration_min: Optional[float] = None
    note: str = ""


class BeerStyle(SQLModel, table=True):
    """Verwaltete Liste der Bierstile (Einstellungen > Bierstile), als
    Auswahl beim Anlegen/Bearbeiten eines Suds. Der Sud selbst speichert
    den Stil weiterhin als reinen Text (Batch.style) - über "Sonstige" +
    Freitext bleibt so auch ein nicht gelisteter Stil möglich, ohne dass
    beim späteren Entfernen eines Listeneintrags bereits gespeicherte Sude
    ihren Stil verlieren."""

    id: Optional[int] = Field(default=None, primary_key=True)
    position: int = 0
    name: str


class Batch(SQLModel, table=True):
    """Ein Sud (entspricht einem Tab in der Excel-Vorlage)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_number: int = Field(index=True)  # bewusst nicht unique: an manchen
    # Brautagen wurden zwei Sude mit derselben Nummer parallel angesetzt
    # (z.B. "Batch #57 Festbier" und "Batch #57 NEIPA" im Originalprotokoll)
    name: str = ""
    style: str = ""
    fermentation_type: str = ""  # "Obergärig" / "Untergärig"
    brew_date: Optional[date] = None
    bottling_date: Optional[date] = None

    target_volume_l: Optional[float] = None  # Ausschlagwürze
    color_ebc: Optional[float] = None

    main_water_l: Optional[float] = None
    sparge_water_l: Optional[float] = None
    lactic_acid_80_ml: Optional[float] = None

    boil_time_min: Optional[float] = None

    target_og_plato: Optional[float] = None  # "geplant"
    pre_lauter_brix: Optional[float] = None
    post_lauter_brix: Optional[float] = None
    post_lauter_volume_l: Optional[float] = None
    water_adjustment_l: Optional[float] = None
    post_boil_brix: Optional[float] = None
    post_boil_volume_l: Optional[float] = None

    # Von Hand im Originalprotokoll eingetragene Werte, als Fallback für
    # Sude, bei denen die App IBU/Alkohol mangels Rohdaten (Alphasäure,
    # Gärverlauf) nicht selbst berechnen kann.
    recorded_ibu: Optional[float] = None
    recorded_abv_text: Optional[str] = None

    # Für historische/bereits abgeschlossene Sude (z.B. nachträglich mit dem
    # Lagerbestand verknüpfte Importe): verhindert, dass das Speichern
    # dieses Suds automatische Lagerbuchungen auslöst oder verändert - die
    # Zutaten wurden ja bereits real verbraucht, ohne dass der aktuelle
    # Bestand rückwirkend etwas damit zu tun haben soll.
    inventory_deduction_locked: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    grain_additions: List["GrainAddition"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "GrainAddition.position"}
    )
    mash_steps: List["MashStep"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "MashStep.position"}
    )
    hop_additions: List["HopAddition"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "HopAddition.position"}
    )
    yeast_additions: List["YeastAddition"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "YeastAddition.position"}
    )
    dry_hop_additions: List["DryHopAddition"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "DryHopAddition.position"}
    )
    carbonation_entries: List["CarbonationEntry"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "CarbonationEntry.position"}
    )
    fermentation_entries: List["FermentationLogEntry"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "FermentationLogEntry.position"}
    )
    brew_day_tasks: List["BrewDayTask"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "BrewDayTask.position"}
    )
    comments: List["BatchComment"] = Relationship(
        back_populates="batch", sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "BatchComment.position"}
    )
    inventory_transactions: List["InventoryTransaction"] = Relationship(back_populates="batch")


class GrainAddition(SQLModel, table=True):
    """Schüttung: eine Malzsorte + Menge."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    malt_name: str
    amount_kg: float = 0
    inventory_item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id")

    batch: Batch = Relationship(back_populates="grain_additions")
    inventory_item: Optional["InventoryItem"] = Relationship()


class MashStep(SQLModel, table=True):
    """Maischplan: eine Rast."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    name: str  # z.B. "Einmaischen", "1. Rast", "Abmaischen"
    temperature_c: Optional[float] = None
    duration_min: Optional[float] = None
    comment: str = ""

    batch: Batch = Relationship(back_populates="mash_steps")


class HopAddition(SQLModel, table=True):
    """Würzekochen: eine Hopfengabe (Kochen, Whirlpool oder
    Nachisomerisierung)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    hop_name: str
    alpha_acid_percent: Optional[float] = None
    amount_g: float = 0
    time_min: Optional[float] = None
    temperature_c: Optional[float] = None
    addition_type: HopAdditionType = HopAdditionType.kochen
    inventory_item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id")
    show_on_label: bool = True  # ob diese Gabe in der Hopfensorten-Zeile des Etiketts auftaucht

    batch: Batch = Relationship(back_populates="hop_additions")


class YeastAddition(SQLModel, table=True):
    """Hefegabe."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    yeast_name: str
    generation_label: str = ""  # z.B. "3. Führung"
    amount: Optional[float] = None
    unit: str = "g"
    pitch_temperature_c: Optional[float] = None
    comment: str = ""
    inventory_item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id")

    batch: Batch = Relationship(back_populates="yeast_additions")


class DryHopAddition(SQLModel, table=True):
    """Stopfhopfen."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    hop_name: str
    timing_label: str = ""
    amount_g: float = 0
    inventory_item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id")

    batch: Batch = Relationship(back_populates="dry_hop_additions")


class CarbonationEntry(SQLModel, table=True):
    """Karbonisierung: Zucker je Flaschengröße."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    sugar_g: float = 0
    bottle_volume_l: float = 0.5
    label: str = "Zucker"

    batch: Batch = Relationship(back_populates="carbonation_entries")


class FermentationLogEntry(SQLModel, table=True):
    """Gärverlauf: eine Messung (Datum + Brix)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    entry_date: Optional[date] = None
    brix: Optional[float] = None
    comment: str = ""

    batch: Batch = Relationship(back_populates="fermentation_entries")


class BrewDayTask(SQLModel, table=True):
    """Brautag-Zeitplan: eine Taetigkeit mit der dafuer tatsaechlich
    benoetigten Dauer (keine Vorab-Planung, sondern eine Erfassung waehrend/
    nach dem Brautag) - direkt auf der Sud-Detailseite eingetragen, entweder
    ueber Beginn/Ende (Dauer wird daraus berechnet) oder als manuelle
    Minutenangabe."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    task_name: str
    start_time: Optional[str] = None  # "HH:MM"
    end_time: Optional[str] = None  # "HH:MM"
    planned_duration_min: Optional[float] = None
    note: str = ""

    batch: Batch = Relationship(back_populates="brew_day_tasks")


class BatchComment(SQLModel, table=True):
    """Freitext-Kommentar/Logeintrag zu einem Sud (mehrere pro Sud möglich,
    wie die Kommentarzeilen am Ende jedes Excel-Tabs)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    entry_date: Optional[date] = None
    text: str

    batch: Batch = Relationship(back_populates="comments")


class InventoryItem(SQLModel, table=True):
    """Ein Lagerbestand-Artikel (Malz, Hopfen oder Hefe)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    category: InventoryCategory
    name: str
    brand: str = ""
    spec: str = ""  # z.B. Alphasäure, Emulsifier
    color_ebc: Optional[float] = None  # Eigenfarbe des Malzes selbst (nur Kategorie Malz)
    amount: float = 0
    unit: str = "kg"
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    transactions: List["InventoryTransaction"] = Relationship(back_populates="item")


class InventoryTransaction(SQLModel, table=True):
    """Buchung auf einen Lagerbestand-Artikel: positiv = Zugang (Einkauf),
    negativ = Abgang (Verbrauch in einem Sud)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="inventoryitem.id")
    batch_id: Optional[int] = Field(default=None, foreign_key="batch.id")
    delta: float
    note: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    item: InventoryItem = Relationship(back_populates="transactions")
    batch: Optional[Batch] = Relationship(back_populates="inventory_transactions")
