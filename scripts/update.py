#!/usr/bin/env python3
"""Free, public-data snapshot builder for Oil Sentinel.

No EIA API key is needed: EIA publishes official per-series XLS files.
Satellites: Element84 Earth Search STAC catalog for Copernicus Sentinel-2 L2A.
Optional imagery: small COG crop of a tank farm; NOT a storage-volume estimate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

import requests

HERE = Path(__file__).resolve().parents[1]
SITE = HERE / "site"
IMAGES = SITE / "images"
USER_AGENT = "OilSentinel/1.0 (+free public-data hobby research; respects rate limits)"
REQUEST_TIMEOUT = 28
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}
STAC = "https://earth-search.aws.element84.com/v1/search"
SITE_LAT = 35.952719
SITE_LON = -96.731958
# Verified historic Cushing tank-farm waypoint; this is ONE representative cluster.
AOI_BBOX = [-96.764, 35.929, -96.699, 35.982]
EIA_SERIES = {
    "cushing": ("W_EPC0_SAX_YCUOK_MBBL", "Cushing crude stocks"),
    "us_crude": ("WCESTUS1", "US commercial crude, ex-SPR"),
    "gasoline": ("WGTSTUS1", "US gasoline stocks"),
    "distillate": ("WDISTUS1", "US distillate stocks"),
}
LOGGER = logging.getLogger("oil-sentinel")
FORECAST_SPECS = {"us_crude": "US_SPEC", "cushing": "CUSHING_SPEC"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def official_excel_url(series_id: str) -> str:
    return f"https://www.eia.gov/dnav/pet/hist_xls/{series_id}w.xls"


def eia_history_url(series_id: str) -> str:
    return f"https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s={series_id}"


def unpack_eia_dataframe(frame: Any, series_id: str, name: str) -> dict:
    """Normalize EIA 'Data 1' sheet; stock values are THOUSAND barrels."""
    import pandas as pd

    if len(frame.columns) < 2:
        raise ValueError(f"EIA {series_id}: expected >= 2 columns")
    # Column names after skiprows=2 are typically 'Date' and the long series title.
    dates = pd.to_datetime(frame.iloc[:, 0], errors="coerce", format="mixed")
    values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    obs = []
    for timestamp, thousands in zip(dates, values):
        if pd.isna(timestamp) or pd.isna(thousands):
            continue
        amount = float(thousands) / 1000.0
        if amount <= 0 or amount > 5000:
            continue
        obs.append({"date": timestamp.date().isoformat(), "mb": round(amount, 3)})
    # EIA may add corrections. Last occurrence of a date wins.
    obs = list({point["date"]: point for point in obs}.values())
    obs.sort(key=lambda p: p["date"])
    if len(obs) < 2:
        raise ValueError(f"EIA {series_id}: fewer than 2 valid weekly records")
    full_history = obs
    obs = obs[-78:]
    current = obs[-1]
    change = round(current["mb"] - obs[-2]["mb"], 3)
    four_weeks = round(current["mb"] - obs[-5]["mb"], 3) if len(obs) >= 5 else None
    return {
        "name": name,
        "series_id": series_id,
        "as_of": current["date"],
        "mb": current["mb"],
        "week_change_mb": change,
        "four_week_change_mb": four_weeks,
        "history": obs,
        "url": eia_history_url(series_id),
        "unit": "million barrels",
        "_full_history": full_history,
    }


def fetch_eia_series(session: requests.Session, series_id: str, name: str) -> dict:
    import pandas as pd

    url = official_excel_url(series_id)
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    if not response.content.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(f"EIA {series_id}: response was not an .xls workbook")
    frame = pd.read_excel(BytesIO(response.content), sheet_name="Data 1", skiprows=2, engine="xlrd")
    return unpack_eia_dataframe(frame, series_id, name)


def pressure_signal(series: dict[str, dict]) -> dict:
    """Simple, explicit, inventory-only heuristic; NOT a price/trade forecast."""
    a = series.get("us_crude")
    b = series.get("cushing")
    if not a or not b or a["as_of"] != b["as_of"]:
        return {"key": "unavailable", "title": "No validated signal", "message": "The US and Cushing series are missing or report different weeks. No inference made."}
    us = float(a["week_change_mb"])
    cu = float(b["week_change_mb"])
    if us <= -1.5 and cu <= -0.4:
        key, title = "tightening", "Broad stock draw"
        meaning = "Both national crude and Cushing inventories are falling meaningfully: potentially supportive for WTI, all else equal."
    elif us >= 1.5 and cu >= 0.4:
        key, title = "loosening", "Broad stock build"
        meaning = "Both national crude and Cushing inventories are building meaningfully: potentially negative for WTI, all else equal."
    elif us < 0 and cu < 0:
        key, title = "lean-tightening", "Inventories drawing"
        meaning = "Both national crude and Cushing fell, but not enough for the stronger stock-draw classification."
    elif us > 0 and cu > 0:
        key, title = "lean-loosening", "Inventories building"
        meaning = "Both national crude and Cushing rose, but not enough for the stronger stock-build classification."
    else:
        key, title = "mixed", "Mixed inventory picture"
        meaning = "National crude and Cushing changed in opposite directions or one was flat. No consistent inventory signal."
    return {"key": key, "title": title, "message": meaning, "method": "Uses current week-over-week US crude and Cushing changes only, not market expectations or WTI chart direction."}


def fetch_stac(session: requests.Session, now: datetime) -> dict:
    start = (now - timedelta(days=65)).date().isoformat()
    end = (now + timedelta(days=1)).date().isoformat()
    params = {"collections": "sentinel-2-l2a", "bbox": ",".join(map(str, AOI_BBOX)), "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100}
    resp = session.get(STAC, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    features = payload.get("features", [])
    # Keep only scenes with a full bounding box containing the monitored tank farm.
    scenes = []
    for item in features:
        props = item.get("properties", {})
        bbox = item.get("bbox", [])
        dt = str(props.get("datetime", ""))
        if len(bbox) < 4 or not (bbox[0] <= SITE_LON <= bbox[2] and bbox[1] <= SITE_LAT <= bbox[3]):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}", dt):
            continue
        cloud = props.get("eo:cloud_cover")
        try:
            cloud = round(float(cloud), 1) if cloud is not None else None
        except (ValueError, TypeError):
            cloud = None
        assets = item.get("assets") or {}
        scene = {
            "id": item.get("id", ""), "date": dt[:10], "datetime": dt,
            "cloud_percent": cloud,
            "stac_url": next((l.get("href") for l in item.get("links", []) if l.get("rel") == "self"), ""),
            "image": None,
            "image_note": "No preview yet",
            "copernicus_url": "https://browser.dataspace.copernicus.eu/?zoom=12&lat=35.952719&lng=-96.731958",
            "_assets": assets,
        }
        scenes.append(scene)
    scenes.sort(key=lambda s: s["datetime"], reverse=True)
    # One scene per date (prefer the cloud-clearest when duplicate satellite tiles exist).
    days = {}
    for scene in scenes:
        old = days.get(scene["date"])
        if old is None or (scene["cloud_percent"] if scene["cloud_percent"] is not None else 999) < (old["cloud_percent"] if old["cloud_percent"] is not None else 999):
            days[scene["date"]] = scene
    scenes = sorted(days.values(), key=lambda s: s["datetime"], reverse=True)[:12]
    return {"status": "live", "catalog": "Element 84 Earth Search, Copernicus Sentinel-2 L2A", "scenes": scenes, "latest_scene_date": scenes[0]["date"] if scenes else None, "resolution_m": 10, "site": {"name": "Representative Cushing tank farm", "latitude": SITE_LAT, "longitude": SITE_LON, "note": "This coordinate tracks one tank-farm cluster, not all Cushing storage."}, "note": "Cloud-cover percent is the satellite tile's overall value, not a verified local tank-level cloud percentage. 10m imagery cannot determine floating-roof fill levels or barrels."}


def save_crop(scene: dict, image_name: str) -> bool:
    """Best effort Cushing RGB crop from public Sentinel-2 Cloud Optimized GeoTIFFs.

    Uses 3-band `visual` when present, otherwise red/green/blue 10m COGs.
    This is illustrative imagery only, never a measured oil inventory value.
    """
    import numpy as np
    from PIL import Image
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    from rasterio.warp import transform as coord_transform

    assets = scene.get("_assets") or {}

    def crop_cog(href: str, bands: list[int]) -> np.ndarray:
        if not href.startswith("https://") or not href.lower().split("?")[0].endswith((".tif", ".tiff")):
            raise ValueError("Asset was not a public HTTPS GeoTIFF")
        with rasterio.open(href) as ds:
            if ds.count < max(bands) or ds.crs is None or ds.crs.is_geographic:
                raise ValueError("No supported georeferenced Sentinel-2 asset")
            x, y = coord_transform("EPSG:4326", ds.crs, [SITE_LON], [SITE_LAT])
            radius = 1850  # metres; Cushing Sentinel-2 tiles are UTM projected
            win = from_bounds(x[0]-radius, y[0]-radius, x[0]+radius, y[0]+radius, transform=ds.transform)
            return ds.read(bands, window=win, out_shape=(len(bands), 512, 512),
                           boundless=True, fill_value=0, resampling=Resampling.bilinear)

    def enhance(arr: np.ndarray) -> np.ndarray:
        if arr.dtype == np.uint8:
            return arr
        clean = arr.astype("float32")
        valid = clean[clean > 0]
        if valid.size < 100:
            raise ValueError("Image did not contain valid site pixels")
        lo, hi = np.percentile(valid, [2, 98])
        if hi <= lo:
            raise ValueError("No dynamic image range")
        return (np.clip((clean-lo)/(hi-lo)*255, 0, 255)).astype("uint8")

    env = {"GDAL_DISABLE_READDIR_ON_OPEN":"EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS":".tif,.tiff",
           "GDAL_HTTP_MAX_RETRY":"2", "GDAL_HTTP_RETRY_DELAY":"1", "GDAL_HTTP_CONNECTTIMEOUT":"8",
           "GDAL_HTTP_TIMEOUT":"30", "AWS_NO_SIGN_REQUEST":"YES"}
    try:
        with rasterio.Env(**env):
            visual = (assets.get("visual") or {}).get("href")
            if visual and visual.lower().split("?")[0].endswith((".tif", ".tiff")):
                try:
                    raw = crop_cog(visual, [1,2,3])
                except Exception as exc:
                    LOGGER.info("Visual COG crop unsuccessful, falling back to RGB bands: %s", exc)
                    raw = None
            else:
                raw = None
            if raw is None:
                missing = [band for band in ("red","green","blue") if not (assets.get(band) or {}).get("href")]
                if missing:
                    LOGGER.info("Missing RGB assets %s for %s", missing, scene["date"])
                    return False
                raw = np.stack([crop_cog(assets[band]["href"], [1])[0] for band in ("red","green","blue")])
        if raw.shape != (3,512,512):
            raise ValueError("Unexpected RGB shape")
        color = np.moveaxis(raw, 0, 2)
        if color.dtype != np.uint8:
            color = np.stack([enhance(color[:,:,i]) for i in range(3)],axis=2)
        if float(color.mean()) < 3:
            raise ValueError("Empty image crop")
        IMAGES.mkdir(exist_ok=True, parents=True)
        Image.fromarray(color, "RGB").save(IMAGES / image_name, optimize=True)
        return True
    except Exception as exc:
        LOGGER.warning("Could not crop Sentinel-2 scene %s: %s", scene["date"], exc)
        return False


def try_market_quote(session: requests.Session) -> dict:
    """Optional free third-party convenience feed, never required for inventory scoring."""
    url = "https://americasoilwatch.com/api/v1/wti"
    resp = session.get(url, headers=HEADERS, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    price = data.get("priceUsd")
    if price is None or not (1 < float(price) < 1000):
        raise ValueError("Price missing or invalid")
    return {"status": "available", "price_usd": float(price), "change_pct": data.get("changePct"), "session_date": data.get("sessionDate"), "observed_at": data.get("observedAt"), "contract": data.get("contractLabel"), "source": "AmericasOilWatch public API (underlying Yahoo Finance, futures quote)", "url": url, "warning": "Third-party delayed/indicative quote. May differ from your USOIL CFD, which is not the same instrument."}


def build_forecast(series: dict[str, dict]) -> dict:
    """Next-report forecasts from full EIA history; see scripts/forecast.py for the tested method."""
    import pandas as pd
    import forecast as fc

    def levels(key: str) -> pd.Series:
        points = series[key].get("_full_history") or []
        return pd.Series([p["mb"] for p in points], index=pd.to_datetime([p["date"] for p in points]))

    forecaster = fc.InventoryForecaster()
    result = {"status": "live"}
    for key, spec_name in FORECAST_SPECS.items():
        result[key] = forecaster.forecast(levels(key), getattr(fc, spec_name))
    result["us_outlook"] = forecaster.outlook(levels("us_crude"))
    if result["us_crude"]["target_week"] != result["cushing"]["target_week"]:
        raise ValueError("US and Cushing forecasts target different weeks")
    return result


WTI_DAILY_SERIES = "RWTC"


def fetch_wti_daily(session: requests.Session):
    """EIA's daily WTI spot price (Cushing), the free official history used for the trader read's track record."""
    import pandas as pd

    url = f"https://www.eia.gov/dnav/pet/hist_xls/{WTI_DAILY_SERIES}d.xls"
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    if not response.content.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError("WTI daily: response was not an .xls workbook")
    frame = pd.read_excel(BytesIO(response.content), sheet_name="Data 1", skiprows=2, engine="xlrd")
    prices = pd.Series(pd.to_numeric(frame.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(frame.iloc[:, 0], errors="coerce"))
    return prices[prices.index.notna()].dropna()


def build_trader_read(series: dict[str, dict], session: requests.Session) -> dict:
    """Bullish / bearish / neutral read of the last report, the next report's levels, and the tested track record."""
    import pandas as pd
    import forecast as fc
    import report_verdict as rv

    def levels(key: str) -> pd.Series:
        points = series[key].get("_full_history") or []
        return pd.Series([p["mb"] for p in points], index=pd.to_datetime([p["date"] for p in points]))

    forecaster = fc.InventoryForecaster()
    products = levels("gasoline").add(levels("distillate")).dropna()
    verdict = rv.ReportVerdict(
        rv.Walk.of(forecaster.walk_forward(levels("us_crude"), fc.US_SPEC)),
        rv.Walk.of(forecaster.walk_forward(levels("cushing"), fc.CUSHING_SPEC)),
        rv.Walk.of(forecaster.walk_forward(products, fc.SeriesSpec("products", "seasonal", 1.0))),
    )
    result = {"status": "live", "latest": verdict.latest(), "levels": verdict.levels()}
    try:
        result["record"] = verdict.track_record(fetch_wti_daily(session))
    except Exception as exc:
        LOGGER.warning("WTI daily prices unavailable, no track record this build: %s", exc)
        result["record"] = {}
    return result


def trader_sentence(read: dict) -> str:
    if read.get("status") != "live":
        return ""
    latest, lv = read["latest"], read.get("levels") or {}
    text = f"Trader's read of that report: {latest['verdict']} for crude. "
    if lv:
        text += f"Next report: bullish if US crude comes in below {lv['bullish_below_mb']:+.1f} million, bearish above {lv['bearish_above_mb']:+.1f} million. "
    return text


def fetch_next_report(session: requests.Session, latest_week: str) -> dict:
    """When the next weekly report is due, from EIA's schedule page (holiday moves) or its standard Wednesday rule."""
    from datetime import date as date_type

    import release_schedule as rs

    try:
        response = session.get(rs.SCHEDULE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        schedule = rs.ReleaseSchedule.from_html(response.text)
    except Exception as exc:
        LOGGER.warning("EIA schedule page unavailable, using the standard rule: %s", exc)
        schedule = rs.ReleaseSchedule()
    return schedule.next_after(date_type.fromisoformat(latest_week))


def next_report_sentence(nxt: dict) -> str:
    if not nxt.get("release_eastern"):
        return ""
    why = f", moved for {nxt['holiday']}" if nxt.get("holiday") else ""
    return f"Next report due {nxt['release_eastern']}{why}. "


def siri_briefing(snapshot: dict) -> str:
    eia = snapshot.get("eia") or {}
    series = eia.get("series") or {}
    cu = series.get("cushing")
    us = series.get("us_crude")
    if snapshot.get("snapshot_mode") == "demo":
        prefix = "Oil Sentinel demo. This is a historical sample, not today's inventory. "
    else:
        prefix = "Oil Sentinel inventory update. "
    if not (cu and us):
        return prefix + "The official EIA inventory series are currently unavailable. No trading conclusion."
    sig = (eia.get("signal") or {}).get("title", "No validated signal")
    return (
        prefix
        + f"Official EIA data for week ending {us['as_of']}. "
        + f"US commercial crude, {us['mb']:.2f} million barrels, weekly change {us['week_change_mb']:+.2f} million. "
        + f"Cushing, {cu['mb']:.2f} million barrels, weekly change {cu['week_change_mb']:+.2f} million. "
        + (trader_sentence(snapshot["trader"]) if (snapshot.get("trader") or {}).get("status") == "live" else f"Inventory assessment: {sig}. ")
        + forecast_sentence(snapshot.get("forecast") or {})
        + next_report_sentence(snapshot.get("next_report") or {})
        + (f"Latest Copernicus scene: {snapshot['satellite']['latest_scene_date']}. " if snapshot.get("satellite", {}).get("latest_scene_date") else "No recent satellite acquisition verified. ")
        + "These are inventory indicators, not a standalone trading signal."
    )


def forecast_sentence(fc: dict) -> str:
    if fc.get("status") != "live":
        return ""
    us, cu = fc["us_crude"], fc["cushing"]
    return (f"Forecast for the report covering week ending {us['target_week']}: "
            f"US crude {us['change_mb']:+.1f} million, likely between {us['low_mb']:+.1f} and {us['high_mb']:+.1f}. "
            f"Cushing {cu['change_mb']:+.1f} million. ")


def build(existing: dict | None = None, session: requests.Session | None = None, now: datetime | None = None, render_images: bool = True) -> dict:
    session = session or requests.Session()
    now = now or utcnow()
    old = existing or {}
    snapshot = {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "snapshot_mode": "live",
        "eia": {"status": "unavailable", "series": {}, "signal": {}},
        "satellite": {"status": "unavailable", "scenes": [], "latest_scene_date": None},
        "market": {"status": "unavailable"},
        "errors": [],
    }
    for key, (sid, name) in EIA_SERIES.items():
        try:
            snapshot["eia"]["series"][key] = fetch_eia_series(session, sid, name)
            LOGGER.info("EIA %-12s %s", key, snapshot["eia"]["series"][key]["as_of"])
        except Exception as exc:
            LOGGER.warning("EIA %s unavailable: %s", key, exc)
            snapshot["errors"].append(f"EIA {key}: {type(exc).__name__}")
            # Never silently relabel a previous or demo datum as freshly fetched.
            prior = (old.get("eia") or {}).get("series", {}).get(key)
            if prior:
                snapshot["eia"]["series"][key] = prior
    series = snapshot["eia"]["series"]
    required = ("cushing", "us_crude")
    if all(k in series for k in required):
        snapshot["eia"]["status"] = "live" if not any(f"EIA {k}:" in err for err in snapshot["errors"] for k in required) else "stale"
    snapshot["eia"]["signal"] = pressure_signal(series) if snapshot["eia"]["status"] == "live" else {"key": "unavailable", "title": "Source needs refresh", "message": "Critical data may be stale. No current inventory assessment."}
    snapshot["forecast"] = {"status": "unavailable", "reason": "EIA history not refreshed on this build."}
    if snapshot["eia"]["status"] == "live":
        try:
            snapshot["forecast"] = build_forecast(series)
        except Exception as exc:
            LOGGER.warning("Forecast unavailable: %s", exc)
            snapshot["errors"].append(f"Forecast: {type(exc).__name__}")
            snapshot["forecast"] = {"status": "unavailable", "reason": "Forecast could not be computed on this build."}
    snapshot["trader"] = {"status": "unavailable", "reason": "EIA history not refreshed on this build."}
    if snapshot["eia"]["status"] == "live" and all(k in series for k in ("gasoline", "distillate")):
        try:
            snapshot["trader"] = build_trader_read(series, session)
        except Exception as exc:
            LOGGER.warning("Trader read unavailable: %s", exc)
            snapshot["errors"].append(f"Trader read: {type(exc).__name__}")
            snapshot["trader"] = {"status": "unavailable", "reason": "The trader read could not be computed on this build."}
    us_week = (series.get("us_crude") or {}).get("as_of")
    snapshot["next_report"] = fetch_next_report(session, us_week) if us_week else {}
    for item in series.values():
        item.pop("_full_history", None)
    try:
        satellite = fetch_stac(session, now)
        # Keep newest two *usable* passes rather than selecting old clearest images.
        candidates = [s for s in satellite["scenes"] if s["cloud_percent"] is None or s["cloud_percent"] <= 55][:2]
        if render_images:
            for scene in candidates:
                fname = f"cushing-{scene['date']}.png"
                if save_crop(scene, fname):
                    scene["image"] = f"images/{fname}"
                    scene["image_note"] = "Actual Sentinel-2 10m RGB crop (illustrative only)"
        for scene in satellite["scenes"]:
            scene.pop("_assets", None)
        snapshot["satellite"] = satellite
    except Exception as exc:
        LOGGER.warning("Satellite catalog unavailable: %s", exc)
        snapshot["errors"].append(f"Satellite catalog: {type(exc).__name__}")
        if (old.get("satellite") or {}).get("scenes"):
            snapshot["satellite"] = dict(old["satellite"])
            snapshot["satellite"]["status"] = "stale"
            for scene in snapshot["satellite"].get("scenes", []):
                if scene.get("image") and not (SITE / scene["image"]).exists():
                    scene["image"] = None
    try:
        snapshot["market"] = try_market_quote(session)
    except Exception as exc:
        LOGGER.warning("Optional WTI price feed unavailable: %s", exc)
        snapshot["errors"].append(f"Price (optional): {type(exc).__name__}")
    if snapshot["eia"]["status"] != "live" or snapshot["satellite"]["status"] != "live":
        snapshot["snapshot_mode"] = "partial"
    return snapshot


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SITE.mkdir(exist_ok=True, parents=True)
    path = SITE / "data.json"
    try:
        old = json.loads(path.read_text()) if path.exists() else None
    except Exception:
        old = None
    snapshot = build(existing=old)
    # Write atomically; don't delete the previous saved snapshot after an exception.
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    (SITE / "briefing.txt").write_text(siri_briefing(snapshot) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %s; EIA=%s STAC=%s", path, snapshot["eia"]["status"], snapshot["satellite"]["status"])
    # A partial build is still published, clearly labelled as such.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
