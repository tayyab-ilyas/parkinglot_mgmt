from fastapi import FastAPI

from app import errors
from app.modules.identity.router import router as identity
from app.modules.locations.router import router as locations
from app.modules.parking.router import router as parking
from app.modules.pricing.router import rates_router as rates
from app.modules.pricing.router import router as pricing
from app.modules.reporting.router import router as reporting

app = FastAPI(title="Parking Lot API")
errors.install(app)
for r in (identity, locations, pricing, rates, parking, reporting):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
