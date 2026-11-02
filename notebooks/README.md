# Notebooks

- `yolo_ppe_training.ipynb` — **restored from git history** (was
  `model/yolomodel/Ironsite Hackathon.ipynb`, commit `cfbaded`). Colab
  workflow: pulls `yihong1120/Construction-Hazard-Detection-YOLO11` from
  HuggingFace, trains YOLO11 on the PPE sample set from Google Drive,
  runs video inference. Needs Drive access for the private 18 GB set —
  see [docs/DATA.md](../docs/DATA.md) for public alternatives.

Previously referenced notebooks (`Posture_sam3_style.ipynb`,
`Sam3_test.ipynb`) were never committed — their logic was folded into the
backend pipeline, which is now the single source of truth:

- Posture / ergonomics → `backend/app/pipeline/posture.py`
- PPE / wall-cam → `backend/app/pipeline/wall_cam.py`
- VLM assessment → `backend/app/pipeline/vlm_step.py`

New notebooks should import from `app.pipeline` instead of copying
REBA / `CLASS_MAP` logic. Commit with outputs stripped (`nbstripout` or
manual clear) — `.gitignore` allows `notebooks/*.ipynb` only.
