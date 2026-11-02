"""Central application settings — every env var lives here.

Loads from ``backend/.env`` plus the process environment. See
``backend/.env.example`` (and the repo-root ``.env.example``) for the full
list with documentation.

Meta Model API: Meta's hosted API at ``https://api.meta.ai`` is
configured with a single key, ``MODEL_API_KEY``. The legacy names
``META_MODEL_API_KEY``, ``META_LLAMA_API_KEY`` and ``LLAMA_API_KEY`` are
still accepted as aliases so existing deployments keep working. No key is
ever committed — the checked-in ``.env.example`` files contain empty
placeholders only.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BACKEND_DIR / "models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # -- app ---------------------------------------------------------------
    app_name: str = "CAGE ML Service"
    # Local-dev default: the dashboard may be served from any local host/port
    # (localhost, 127.0.0.1, LAN IP). Restrict via CORS_ORIGINS in production.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        alias="CORS_ORIGINS",
    )
    prewarm_models: bool = Field(default=True, alias="PREWARM_MODELS")

    # -- database ----------------------------------------------------------
    database_url: str = Field(
        default=f"sqlite:///{BACKEND_DIR / 'data' / 'cage.db'}",
        alias="DATABASE_URL",
    )

    # -- job outputs -------------------------------------------------------
    jobs_dir: Path = Field(default=BACKEND_DIR / "jobs", alias="JOBS_DIR")

    # -- local model weights (repo-relative; override via env) -------------
    yolo_model_path: Path = Field(
        default=MODELS_DIR / "last.pt", alias="YOLO_MODEL_PATH"
    )
    sam_model_path: Path = Field(default=MODELS_DIR / "sam3.pt", alias="SAM_MODEL_PATH")
    pose_model_path: Path = Field(
        default=MODELS_DIR / "yolo26l-pose.pt", alias="POSE_MODEL_PATH"
    )
    posture_cuda_device: str | None = Field(default=None, alias="POSTURE_CUDA_DEVICE")

    # -- VLM (stage 3) ------------------------------------------------------
    # "local" = Qwen3-VL weights on GPU, "meta" = Meta Model API (needs key).
    vlm_backend: Literal["local", "meta"] = Field(default="local", alias="VLM_BACKEND")
    vlm_model_id: str = Field(default=str(MODELS_DIR / "qwen3-vl"), alias="VLM_MODEL_ID")
    vlm_adapter_path: str = Field(
        default=str(MODELS_DIR / "adapter1"), alias="VLM_ADAPTER_PATH"
    )
    vlm_gpu_id: str | None = Field(default=None, alias="VLM_GPU_ID")
    vlm_max_pixels: int = Field(default=100352, alias="VLM_MAX_PIXELS")
    vlm_max_new_tokens: int = Field(default=1024, alias="VLM_MAX_NEW_TOKENS")
    vlm_max_new_tokens_pass1: int = Field(
        default=768, alias="VLM_MAX_NEW_TOKENS_PASS1"
    )
    vlm_max_new_tokens_pass2: int = Field(
        default=1024, alias="VLM_MAX_NEW_TOKENS_PASS2"
    )
    vlm_max_annotated_frames: int = Field(
        default=15, alias="VLM_MAX_ANNOTATED_FRAMES"
    )
    vlm_video_fps: float = Field(default=1.0, alias="VLM_VIDEO_FPS")
    vlm_max_hazard_frames: int = Field(default=40, alias="VLM_MAX_HAZARD_FRAMES")
    vlm_chunk_seconds: float = Field(default=60.0, alias="VLM_CHUNK_SECONDS")
    vlm_chunk_frames: int = Field(default=0, alias="VLM_CHUNK_FRAMES")

    # -- Segmentation (stage 2) ------------------------------------------------
    # "local" = SAM weights on GPU, "meta" = SAM 3.1 over the Meta Model API.
    sam_backend: Literal["local", "meta"] = Field(default="local", alias="SAM_BACKEND")

    # -- Meta Model API (https://api.meta.ai) --------------------------------
    # Paste your key into backend/.env as MODEL_API_KEY. Older names
    # (META_MODEL_API_KEY, META_LLAMA_API_KEY, LLAMA_API_KEY) still work.
    meta_model_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "MODEL_API_KEY",
            "META_MODEL_API_KEY",
            "META_LLAMA_API_KEY",
            "LLAMA_API_KEY",
        ),
    )
    meta_model_api_base_url: str = Field(
        default="https://api.meta.ai/v1",
        validation_alias=AliasChoices("META_MODEL_API_BASE_URL", "META_LLAMA_BASE_URL"),
    )
    # Segmentation model for Stage-2 refinement + POST /meta/segment.
    meta_model_api_sam_model: str = Field(
        default="sam-3.1", alias="META_MODEL_API_SAM_MODEL"
    )
    # Cap on flagged frames sent to SAM 3.1 per pipeline job.
    meta_sam_max_frames: int = Field(default=8, alias="META_SAM_MAX_FRAMES")
    # Vision-capable model for Stage-3 VLM assessment (images + detections).
    # Verified live against api.meta.ai (text + image input both work).
    meta_model_api_vision_model: str = Field(
        default="muse-spark-1.3",
        validation_alias=AliasChoices(
            "META_MODEL_API_VISION_MODEL", "META_LLAMA_VISION_MODEL"
        ),
    )
    # Text model for shift-report summaries (verified live).
    meta_model_api_text_model: str = Field(
        default="muse-spark-1.3",
        validation_alias=AliasChoices("META_MODEL_API_TEXT_MODEL", "META_LLAMA_TEXT_MODEL"),
    )
    meta_model_api_timeout_s: float = Field(
        default=120.0,
        validation_alias=AliasChoices("META_MODEL_API_TIMEOUT_S", "META_LLAMA_TIMEOUT_S"),
    )

    # -- backwards-compatible aliases (existing code/tests) -----------------
    @property
    def meta_llama_api_key(self) -> str:  # noqa: D102 - legacy alias
        return self.meta_model_api_key

    @meta_llama_api_key.setter
    def meta_llama_api_key(self, value: str) -> None:
        object.__setattr__(self, "meta_model_api_key", value)

    @property
    def meta_llama_base_url(self) -> str:
        return self.meta_model_api_base_url

    @meta_llama_base_url.setter
    def meta_llama_base_url(self, value: str) -> None:
        object.__setattr__(self, "meta_model_api_base_url", value)

    @property
    def meta_llama_vision_model(self) -> str:
        return self.meta_model_api_vision_model

    @meta_llama_vision_model.setter
    def meta_llama_vision_model(self, value: str) -> None:
        object.__setattr__(self, "meta_model_api_vision_model", value)

    @property
    def meta_llama_text_model(self) -> str:
        return self.meta_model_api_text_model

    @meta_llama_text_model.setter
    def meta_llama_text_model(self, value: str) -> None:
        object.__setattr__(self, "meta_model_api_text_model", value)

    @property
    def meta_llama_timeout_s(self) -> float:
        return self.meta_model_api_timeout_s

    @meta_llama_timeout_s.setter
    def meta_llama_timeout_s(self, value: float) -> None:
        object.__setattr__(self, "meta_model_api_timeout_s", value)

    @property
    def meta_configured(self) -> bool:
        return bool(self.meta_model_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
