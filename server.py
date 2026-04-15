"""
Web server FastAPI per il sistema Turni PDM.
Espone query treni, stazioni, turn builder e upload PDF via HTTP.

Struttura modulare:
  api/       — router FastAPI (auth, health, trains, validation, builder, shifts, etc.)
  services/  — logica di business (timeline, segments)
  api/deps.py — dipendenze condivise (database, JWT auth)
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.auth import router as auth_router
from api.health import router as health_router
from api.upload import router as upload_router
from api.trains import router as trains_router
from api.validation import router as validation_router
from api.builder import router as builder_router
from api.shifts import router as shifts_router
from api.importers import router as importers_router
from api.viaggiatreno import router as vt_router

app = FastAPI(
    title="Turni PDM API",
    description="API per interrogazione treni e costruzione turni personale di macchina",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers PRIMA del mount static (priorità alle API)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(upload_router)
app.include_router(trains_router)
app.include_router(validation_router)
app.include_router(builder_router)
app.include_router(shifts_router)
app.include_router(importers_router)
app.include_router(vt_router)

# Serve frontend: React build (frontend/dist/) in produzione, static/ come fallback
# DOPO i router — così le API hanno priorità
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
STATIC_DIR = Path(__file__).parent / "static"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
elif STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
