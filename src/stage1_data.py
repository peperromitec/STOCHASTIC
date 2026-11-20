"""Load and clean the Ecobici trip files with the Stage 1 rules.

The functions reproduce, without changes to their logic, the cleaning steps in
``stage1.ipynb`` (sections "Combine dates and times", "Analysis scope and
cleaning rules" and "Station catalog and trip-code matching"). Other notebooks
import them so every analysis starts from the same clean events.

If a rule changes in ``stage1.ipynb``, update it here as well; notebooks that
use this module check the retained event counts against the Stage 1 results.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")

SERVICE_DAY_START = pd.Timedelta(hours=5)            # a service day runs from 05:00 to 04:59 of the next calendar day
CLOSING_OFFSET = pd.Timedelta(hours=19, minutes=30)  # 00:30 = 19.5 h after 05:00
MAX_DURATION_MINUTES = 24 * 60                       # only very extreme trips are discarded

EVENT_COLUMNS = {"pickup": "Ciclo_Estacion_Retiro", "dropoff": "Ciclo_EstacionArribo"}

# Event counts retained in stage1.ipynb ("Cleaning findings"); used as a consistency check.
STAGE1_RETAINED = {
    2026: {"pickup": 1_265_117, "dropoff": 1_265_133},
    2025: {"pickup": 1_435_154, "dropoff": 1_435_174},
}


def load_trips(year, data_dir=DATA_DIR):
    """Read one October file as text, preserving identifiers such as leading zeros."""
    return pd.read_csv(
        Path(data_dir) / f"{year}-10.csv.gz",
        compression="gzip",
        encoding="utf-8-sig",
        dtype="string",
        keep_default_na=False,
    )


def add_trip_times(trips):
    """Add pickup and drop-off timestamps and trip duration in minutes."""
    pickup_at = pd.to_datetime(
        trips["Fecha_Retiro"] + " " + trips["Hora_Retiro"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )
    dropoff_at = pd.to_datetime(
        trips["Fecha_Arribo"] + " " + trips["Hora_Arribo"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )
    return trips.assign(
        pickup_at=pickup_at,
        dropoff_at=dropoff_at,
        duration_minutes=(dropoff_at - pickup_at).dt.total_seconds() / 60,
    )


def clean_events(trips, year):
    """Apply the scope rules to pickup and drop-off events; return clean events and a log."""
    month_start = pd.Timestamp(year=year, month=10, day=1)
    month_end = month_start + pd.offsets.MonthBegin(1)
    too_long = trips["duration_minutes"].gt(MAX_DURATION_MINUTES)
    clean, log = {}, []

    for event, station_column in EVENT_COLUMNS.items():
        timestamps = trips[f"{event}_at"]
        # Events between 00:00 and 04:59 belong to the previous service day.
        shifted = timestamps - SERVICE_DAY_START
        service_date = shifted.dt.normalize()
        after_closing = (shifted - service_date).ge(CLOSING_OFFSET)

        # Rules are applied in order; each row counts only under the first rule that removes it.
        rules = {
            "1. Service date outside October": ~(service_date.ge(month_start) & service_date.lt(month_end)),
            "2. Trip longer than 24 h": too_long,
            "3. Service date on a weekend": service_date.dt.dayofweek.ge(5),
            # Drop-offs after closing are kept: they finish trips that started while the system was open.
            "4. Pickup after closing (00:30–05:00)": after_closing if event == "pickup" else pd.Series(False, index=trips.index),
        }
        keep = pd.Series(True, index=trips.index)
        log.append({"year": year, "event": event, "step": "0. Rows in file", "records": len(trips)})
        for step, mask in rules.items():
            log.append({"year": year, "event": event, "step": step, "records": -int((keep & mask).sum())})
            keep &= ~mask
        log.append({"year": year, "event": event, "step": "5. Events retained", "records": int(keep.sum())})
        if event == "dropoff":
            log.append({"year": year, "event": event, "step": "   of which: drop-offs after closing (kept)",
                        "records": int((keep & after_closing).sum())})

        clean[event] = pd.DataFrame({
            "station": trips.loc[keep, station_column],
            "timestamp": timestamps[keep],
            "service_date": service_date[keep],
            "hour": timestamps[keep].dt.hour.astype("Int8"),
            "duration_minutes": trips.loc[keep, "duration_minutes"],
        })
    return clean, log


def load_clean_events(year, data_dir=DATA_DIR, check=True):
    """Load one October file and return its clean events and cleaning log.

    With ``check=True``, stop if the retained counts differ from stage1.ipynb.
    """
    clean, log = clean_events(add_trip_times(load_trips(year, data_dir)), year)
    if check and year in STAGE1_RETAINED:
        for event, expected in STAGE1_RETAINED[year].items():
            if len(clean[event]) != expected:
                raise ValueError(
                    f"{year} {event}s: {len(clean[event]):,} retained, expected {expected:,} from stage1.ipynb."
                )
    return clean, log


def load_station_catalog(data_dir=DATA_DIR, snapshot="2026-11-19"):
    """Read the saved GBFS station snapshot after verifying its checksum."""
    catalog_path = Path(data_dir) / f"station_information_{snapshot}.json"
    catalog_bytes = catalog_path.read_bytes()
    catalog_metadata = json.loads(catalog_path.with_suffix(".metadata.json").read_text())
    if hashlib.sha256(catalog_bytes).hexdigest() != catalog_metadata["sha256"]:
        raise ValueError("Station snapshot does not match its recorded checksum.")

    stations = pd.DataFrame(json.loads(catalog_bytes)["data"]["stations"])
    catalog = stations[["short_name", "station_id", "name", "lat", "lon", "capacity"]].copy()
    catalog[["short_name", "station_id", "name"]] = catalog[["short_name", "station_id", "name"]].astype("string")
    if catalog["short_name"].isna().any() or catalog["short_name"].str.strip().eq("").any() or catalog["short_name"].duplicated().any():
        raise ValueError("Resolve missing or duplicated public station codes before joining.")
    return catalog
