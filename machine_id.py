# -*- coding: utf-8 -*-
"""Machine ID helper (same scheme as CargoMate).

Run standalone to print this machine's code:
    python machine_id.py

The code is generated from the Windows MachineGuid registry value
(readable without administrator rights) and stored locally on first use.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MACHINE_ID_FILE = os.path.join(DATA_DIR, "machine_id")


def raw_machine_id():
    """Stable machine fingerprint; needs NO administrator rights."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        mid = str(guid).strip().lower()
        if mid:
            return mid
    except Exception:
        pass
    import uuid
    return str(uuid.getnode()).lower()


def get_machine_id():
    """Return the stored machine id, creating it on first use."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(MACHINE_ID_FILE):
        with open(MACHINE_ID_FILE, "r", encoding="utf-8") as f:
            mid = f.read().strip()
            if mid:
                return mid
    mid = raw_machine_id()
    with open(MACHINE_ID_FILE, "w", encoding="utf-8") as f:
        f.write(mid)
    return mid


if __name__ == "__main__":
    print(get_machine_id())
