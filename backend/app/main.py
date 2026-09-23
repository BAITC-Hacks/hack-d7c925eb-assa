from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import database_ready


if not database_ready():
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "import_dataset.py")],
        check=True,
    )

from .routes import router  # noqa: E402


app = FastAPI(title="Career Quest API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Career Quest API", "docs": "/docs"}
