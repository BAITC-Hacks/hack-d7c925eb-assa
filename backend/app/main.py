from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import database_ready, DB_PATH
from .config import load_env
import os


if not DB_PATH.exists():
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "import_dataset.py")],
        check=True,
    )

if not database_ready():
    raise RuntimeError('База повреждена или пуста. Восстановите резервную копию; автоматический сброс отключён.')

from .routes import router  # noqa: E402


app = FastAPI(title="Career Quest API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CQ_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Career Quest API", "docs": "/docs"}
