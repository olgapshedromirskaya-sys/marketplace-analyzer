from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

# Статика
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")

# Главная страница сайта
@app.get("/")
async def root():
    return FileResponse(os.path.join(WEBAPP_DIR, "index.html"))

# Health-check для Railway
@app.get("/health")
async def health():
    return {"status": "ok"}
