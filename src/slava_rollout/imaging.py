from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image


def encode_png_b64(frame: np.ndarray) -> str:
    """RGB uint8 HxWx3 array -> base64-encoded PNG string, for the env-worker HTTP responses."""
    image = Image.fromarray(np.asarray(frame, dtype=np.uint8)[..., :3])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def decode_png_b64(data: str) -> np.ndarray:
    raw = base64.b64decode(data)
    return np.array(Image.open(io.BytesIO(raw)).convert("RGB"))


def save_png(frame: np.ndarray, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(frame, dtype=np.uint8)[..., :3]).save(path)
