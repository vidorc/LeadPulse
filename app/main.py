from fastapi import FastAPI

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.db.session import engine
from app.db.base import Base
from app.api.routes.leads import router as lead_router
import app.models.lead

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0"
)

app.include_router(health_router)
app.include_router(lead_router)

@app.get("/")
def root():
    return {
        "message": "LeadPulse Agent Running"
    }