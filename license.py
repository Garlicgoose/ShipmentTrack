# -*- coding: utf-8 -*-
"""Startup verification for Shipment Track (auto, no dot to click).

Same scheme as CargoMate:
- Network-first: a JSON file on GitHub maps machine ids to an on/off switch.
    {
      "8e4f165a-8457-44c9-897d-3474081bc494": true,   <- this machine, ON
      "8e4f999a-8457-44c9-897d-3474081bc494": false   <- that machine, OFF
    }
- 6-hour grace after a successful network check.
- Network unreachable: local time-window fallback (2026-10-01).
- On failure the app shows a neutral ENGLISH error and exits
  (nothing reveals licensing to colleagues).
"""
import json
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

import machine_id

LICENSE_URL = ("https://raw.githubusercontent.com/Garlicgoose/"
               "MyWorkTool_License/main/ShipmentTrack_license.json")
LOCAL_EXPIRY = date(2026, 10, 1)
REFRESH_HOURS = 0  # 0 = 每次启动都联网检查授权，不做小时级缓存（用户 2026-09-01 要求）
CACHE_FILE = Path(machine_id.DATA_DIR) / "license_cache"

NETWORK_ERROR_MSG = "Unable to start. Please try again."
NOT_AUTHORIZED_MSG = "Unable to start. Please try again."
LOCAL_EXPIRED_MSG = "Unable to start. Please try again."


def fetch_network_license(url, timeout=6):
    """GET the JSON file and parse it."""
    req = urllib.request.Request(url, headers={"User-Agent": "ShipmentTrack/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_network(url, machine_code):
    """True only when the JSON contains {"<machine_code>": true}."""
    data = fetch_network_license(url)
    return bool(data.get(machine_code))


def check_local():
    return date.today() <= LOCAL_EXPIRY


# ---------------- 6-hour grace cache ----------------

def _read_cache():
    try:
        ts = float(CACHE_FILE.read_text(encoding="utf-8").strip())
        return ts
    except Exception:
        return None


def _write_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _clear_cache():
    try:
        CACHE_FILE.unlink()
    except Exception:
        pass


def verify(machine_code, url=None):
    """Return (ok, mode, error_msg).

    - 6h grace: a previous network OK skips the check for REFRESH_HOURS.
    - Network reachable: its answer wins (404 / false / missing -> blocked).
    - Network unreachable: local time-window fallback.
    url defaults to LICENSE_URL; pass an empty string to force local-only.
    """
    url = LICENSE_URL if url is None else url
    if url:
        ts = _read_cache()
        if ts is not None and (time.time() - ts) < REFRESH_HOURS * 3600:
            return True, "cached", None
    if not url:
        ok = check_local()
        return ok, "local", (None if ok else LOCAL_EXPIRED_MSG)
    try:
        ok = check_network(url, machine_code)
        if ok:
            _write_cache()
            return True, "network", None
        _clear_cache()
        return False, "network", NOT_AUTHORIZED_MSG
    except urllib.error.HTTPError as exc:
        # 文件不存在/权限错误：网络是通的但授权文件拿不到 -> 拦截
        if exc.code == 404:
            _clear_cache()
            return False, "network", NOT_AUTHORIZED_MSG
        ok = check_local()
        return ok, "local-fallback", (None if ok else LOCAL_EXPIRED_MSG)
    except Exception:
        # 超时 / DNS / 连接拒绝等：视为断网，回退本地时间窗
        ok = check_local()
        return ok, "local-fallback", (None if ok else LOCAL_EXPIRED_MSG)
