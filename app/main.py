import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, SessionLocal
from app.seed_data import seed_database
from app.routers import (
    auth_router,
    buildings_router,
    energy_router,
    dss_router,
    feedback_router,
    management_router,
    dataset_router,
    ml_router,
    audit_router,
    reports_router
)

# Initialize Database Schema
Base.metadata.create_all(bind=engine)

# Run Seed Data initialization
db = SessionLocal()
try:
    seed_database(db)
finally:
    db.close()

app = FastAPI(
    title="DSS-1.0 — Campus Energy Decision Support System",
    description="Offline-first, deterministic, advisory-only intelligence platform for university peak demand management (Case 05: The 4 PM Spike).",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include API Routers
app.include_router(auth_router.router)
app.include_router(buildings_router.router)
app.include_router(energy_router.router)
app.include_router(dss_router.router)
app.include_router(feedback_router.router)
app.include_router(management_router.router)
app.include_router(dataset_router.router)
app.include_router(ml_router.router)
app.include_router(audit_router.router)
app.include_router(reports_router.router)

# Page Routes specified by PRD
@app.get("/", response_class=HTMLResponse)
def get_landing_page():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/login/electrician", response_class=HTMLResponse)
def get_electrician_login_page():
    return FileResponse(STATIC_DIR / "login_electrician.html")

@app.get("/login/management", response_class=HTMLResponse)
def get_management_login_page():
    return FileResponse(STATIC_DIR / "login_management.html")

@app.get("/electrician", response_class=HTMLResponse)
def get_electrician_dashboard():
    return FileResponse(STATIC_DIR / "electrician_dashboard.html")

@app.get("/management", response_class=HTMLResponse)
def get_management_dashboard():
    return FileResponse(STATIC_DIR / "management_dashboard.html")

@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "system": "DSS-1.0 Campus Energy Intelligence",
        "mode": "OFFLINE_FIRST",
        "advisory_only": True,
        "rule_version": "DSS-CORE-V1.0"
    }

@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return FileResponse(STATIC_DIR / "robots.txt", media_type="text/plain")

@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    return FileResponse(STATIC_DIR / "sitemap.xml", media_type="application/xml")
