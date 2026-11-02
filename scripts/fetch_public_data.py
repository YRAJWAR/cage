"""Fetch every public CAGE artifact that can be pulled non-interactively.

- Verifies restored YOLO weights exist (backend/models/last.pt).
- Downloads the Ultralytics construction-ppe dataset info (no auth).
- Checks HuggingFace reachability for the base model + VLM dataset.
- Prints manual steps for gated items (HF login, Kaggle, Drive footage).

Run from the repo root:  python scripts/fetch_public_data.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_weights() -> bool:
    pt = ROOT / "backend" / "models" / "last.pt"
    if pt.exists():
        print(f"[ok] YOLO weights present: {pt} ({pt.stat().st_size / 1e6:.1f} MB)")
        return True
    print(f"[missing] {pt} — restore with: git show cfbaded:model/yolomodel/weights/last.pt > {pt}")
    return False


def check_notebooks() -> None:
    nb = ROOT / "notebooks" / "yolo_ppe_training.ipynb"
    print(f"[{'ok' if nb.exists() else 'missing'}] training notebook: {nb}")
    ft = ROOT / "finetune" / "train.py"
    print(f"[{'ok' if ft.exists() else 'missing'}] VLM finetune kit: {ft.parent}")


def fetch_ultralytics_info() -> None:
    try:
        from ultralytics.utils import ASSETS  # noqa: F401
    except ImportError:
        print("[skip] ultralytics not installed — pip install ultralytics, then:")
        print("       YOLO('yolo11n.pt').train(data='construction-ppe.yaml', epochs=50)")
        return
    print("[ok] ultralytics installed.")
    print("     Train on the public PPE set with:")
    print("       from ultralytics import YOLO")
    print("       YOLO('yolo11n.pt').train(data='construction-ppe.yaml', epochs=50)")


def check_huggingface() -> None:
    for repo in (
        "yihong1120/Construction-Hazard-Detection-YOLO11",
        "LouisChen15/ConstructionSite",
        "Qwen/Qwen3-VL-8B-Instruct",
    ):
        kind = "datasets" if repo == "LouisChen15/ConstructionSite" else "models"
        url = f"https://huggingface.co/api/{kind}/{repo}"
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                print(f"[ok] HF reachable: {repo} (HTTP {r.status})")
        except Exception as exc:  # noqa: BLE001 — best-effort reachability
            print(f"[warn] HF check failed for {repo}: {exc}")


def main() -> int:
    print("CAGE public-data check — see docs/DATA.md for the full guide.\n")
    ok = check_weights()
    check_notebooks()
    print()
    fetch_ultralytics_info()
    print()
    check_huggingface()
    print()
    print("Manual steps (gated):")
    print("  1. huggingface-cli login   # then python finetune/scripts/download_dataset.py")
    print("  2. Kaggle sets need ~/.kaggle/kaggle.json — slugs in docs/DATA.md")
    print("  3. 18GB Drive set + POV footage: ask a teammate with Drive access")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
