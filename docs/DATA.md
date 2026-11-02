# Data, weights & datasets

Where everything lives, what was lost, and exact commands to get what remains.

## TL;DR — what works right now with zero downloads

| Artifact | Location | Status |
|---|---|---|
| Fine-tuned YOLO PPE weights (19 MB) | `backend/models/last.pt` | Restored from git history — pipeline runs |
| YOLO training notebook (Colab) | `notebooks/yolo_ppe_training.ipynb` | Restored from git history |
| VLM finetune kit (train/infer/eval + guides) | `finetune/` | Restored from git history |
| VLM dataset (ConstructionSite 10k) | HuggingFace `LouisChen15/ConstructionSite` | Public — one command below |
| PPE dataset (Ultralytics) | `yolo show` / Ultralytics API | Public — one command below |
| Base hazard model | HF `yihong1120/Construction-Hazard-Detection-YOLO11` | Public |
| Kaggle PPE sets, CWPV videos | Links below | Public, manual download |

## What was lost (and why)

These were referenced in the original README but **never committed** — they
lived on a private GPU box (`/workspace`) and Google Drive:

- `Posture_sam3_style.ipynb`, `Sam3_test.ipynb` — experiment notebooks.
  Their logic (REBA angles, `CLASS_MAP`, worker safety log) is now the
  backend pipeline itself: `backend/app/pipeline/posture.py`,
  `wall_cam.py`. Nothing to recover; the backend is the source of truth.
- `analyze_pov_posture_timestamps.py`, `analyze_pov_ppe_timestamps.py` —
  POV timestamp CLIs. Superseded by `POST /process/pov` +
  `GET /jobs/{id}/results`.
- `ergonomic/mvp.py` — mentioned once, never committed anywhere.
- `Sample_Dataset_25k` / full 18 GB training set — private Google Drive
  (`MyDrive/dataset/Sample_Dataset_25k`). Ask a teammate with Drive
  access, or retrain on the public sets below.
- POV/facility video + `Testing_Data_*` clips — private footage, never
  committed. Use your own site video or the public sets below.
- `/workspace/models/{sam3.pt,qwen3-vl,adapter1,yolo26l-pose.pt}` — GPU-box
  weights. Replacements: SAM via Meta API (`SAM_BACKEND=meta`), Qwen3-VL
  from HuggingFace, YOLO-pose from Ultralytics (commands below).

## Download commands

```bash
# 1) PPE image dataset for YOLO (re)training — Ultralytics, public
yolo settings datasets_dir=./datasets
python -c "from ultralytics.utils import ASSETS; print(ASSETS)"
# then in Python:
#   from ultralytics import YOLO
#   YOLO("yolo11n.pt").train(data="construction-ppe.yaml", epochs=50)
# Dataset doc: https://docs.ultralytics.com/datasets/detect/construction-ppe/

# 2) VLM finetune dataset (ConstructionSite 10k) — HuggingFace, accept terms first
huggingface-cli login
python finetune/scripts/inspect_dataset.py     # peek at columns
python finetune/scripts/download_dataset.py    # cache train split

# 3) Base hazard-detection YOLO11 (the notebook's starting point)
huggingface-cli download yihong1120/Construction-Hazard-Detection-YOLO11

# 4) Qwen3-VL base (only for VLM_BACKEND=local)
python finetune/scripts/download_model.py

# 5) YOLO pose model (only for local posture; needs ultralytics)
yolo download yolo26l-pose.pt   # or any *-pose.pt, then set POSE_MODEL_PATH
```

Or run the helper, which fetches what is fetchable and reports the rest:

```bash
python scripts/fetch_public_data.py
```

## Manual downloads (gated / Kaggle)

- CWPV working-posture videos (Figshare):
  https://figshare.com/articles/dataset/CWPV_A_Working_Postures_of_the_Construction_Working_Postures_Videos_dataset/27907818
- Safe/unsafe behaviour videos (Mendeley): https://data.mendeley.com/datasets/xjmtb22pff/1
- Kaggle PPE sets (needs `kaggle.json` credentials):
  - `snehilsanyal/construction-site-safety-image-dataset-roboflow`
  - `ketakichalke/ppe-kit-detection-construction-site-workers`
  - `shlokraval/ppe-dataset-yolov8`
  - `beyzakucuk/ppe-detection-v1`
  - `mugheesahmad/sh17-dataset-for-ppe-detection`

```bash
pip install kaggle   # put kaggle.json in ~/.kaggle/
kaggle datasets download -d snehilsanyal/construction-site-safety-image-dataset-roboflow -p datasets/ -q
```

## Where to put things

```
backend/models/last.pt        YOLO PPE weights (already restored)
backend/models/sam3.pt        local SAM 3 (or SAM_BACKEND=meta)
backend/models/qwen3-vl/      local VLM base (or VLM_BACKEND=meta)
backend/models/yolo26l-pose.pt
datasets/                     training/validation data (gitignored)
```

Never commit footage, weights, or datasets — all are gitignored.
