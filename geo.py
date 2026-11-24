"""Offline IP geolocation with the DB-IP "IP to City Lite" database (CC BY 4.0, https://db-ip.com).

Only country code, country name, region and city are read. Coordinates are never used.
If the database file is missing the lookup returns empty fields and the app keeps working.
"""
import logging
import os
import threading
from typing import Optional

try:
    import maxminddb
except ImportError:  # pragma: no cover
    maxminddb = None

logger = logging.getLogger(__name__)

EMPTY = {"country_code": None, "country": None, "region": None, "city": None}
_lock = threading.Lock()
_reader = None
_reader_path: Optional[str] = None
_missing_logged = False


def db_path() -> str:
    return os.getenv("GEOIP_DB_PATH", "data/dbip-city-lite.mmdb")


def _open(path: str):
    global _reader, _reader_path, _missing_logged
    with _lock:
        if _reader is not None and _reader_path == path:
            return _reader
        if maxminddb is None or not os.path.isfile(path):
            if not _missing_logged:
                logger.warning("GeoIP database not found at %s; location fields will be empty.", path)
                _missing_logged = True
            return None
        # MODE_MMAP keeps the file out of process memory (pages load on demand).
        _reader = maxminddb.open_database(path, mode=maxminddb.MODE_MMAP)
        _reader_path = path
        return _reader


def _name(obj: Optional[dict]) -> Optional[str]:
    if not obj:
        return None
    names = obj.get("names") or {}
    return (names.get("en") or next(iter(names.values()), None))


def lookup(ip: Optional[str], path: Optional[str] = None) -> dict:
    """IP address -> {country_code, country, region, city}; any field may be None."""
    if not ip:
        return dict(EMPTY)
    reader = _open(path or db_path())
    if reader is None:
        return dict(EMPTY)
    try:
        rec = reader.get(ip)
    except (ValueError, OSError):  # not an IP address, or a corrupt file
        return dict(EMPTY)
    if not rec:
        return dict(EMPTY)
    country = rec.get("country") or {}
    subdivisions = rec.get("subdivisions") or []
    return {
        "country_code": country.get("iso_code"),
        "country": _name(country),
        "region": _name(subdivisions[0]) if subdivisions else None,
        "city": _name(rec.get("city")),
    }
