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


class DefaultBrewDayTask(SQLModel, table=True):
    """Vorlage-Position für den Brautag-Zeitplan, die bei einem neuen Sud
    automatisch vorbelegt wird (editierbar unter Einstellungen)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    position: int = 0
    task_name: str
    planned_duration_min: Optional[float] = None
    note: str = ""


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
    """Brautag-Zeitplan: eine Tätigkeit mit geplanter Dauer."""

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batch.id")
    position: int = 0
    task_name: str
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
