import logging
import sys
import os

# Ensure backend/ is on the path regardless of cwd
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db.database import init_db
from api.auth import router as auth_router
from api.jobs import router as jobs_router
from api.agent import router as agent_router
from api.profile import router as profile_router
from api.ats import router as ats_router
from api.stats import router as stats_router
from config import FRONTEND_ORIGIN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="JobAgent API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(agent_router)
app.include_router(profile_router)
app.include_router(ats_router)
app.include_router(stats_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}
