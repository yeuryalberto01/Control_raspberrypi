"""
Simple watchdog script to verify service health and trigger systemd restart.
"""

from __future__ import annotations

import os
import sys

import requests

WATCHDOG_URL = os.getenv("WATCHDOG_URL", "http://127.0.0.1:8000/health")
WATCHDOG_SERVICE = os.getenv("WATCHDOG_SERVICE", "tuapp.service")


def main() -> int:
    try:
        response = requests.get(WATCHDOG_URL, timeout=5)
        if response.status_code == 200:
            print("ok")
            return 0
    except requests.RequestException as exc:
        print(f"watchdog request failed: {exc}")

    print(f"reiniciando {WATCHDOG_SERVICE}")
    os.system(f"sudo /bin/systemctl restart {WATCHDOG_SERVICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
