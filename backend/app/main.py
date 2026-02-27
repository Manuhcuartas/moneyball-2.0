from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(
    title="Moneyball 2.0 API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.get("/")
def root():
    return {"message": "Moneyball 2.0 - Backend Operativo 🏀"}
