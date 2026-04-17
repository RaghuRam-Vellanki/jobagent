import os
from dotenv import load_dotenv

load_dotenv()

# Project root (two levels up from this file: backend/config.py → jobagent/)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_DIR = os.path.join(ROOT_DIR, "resume")
DATA_DIR = os.path.join(ROOT_DIR, "data")

# Title filters (shared across all agents)
TITLE_WHITELIST = [
    "product manager", "product owner", "apm", "associate product",
    "program manager", "product analyst", "product lead",
    "business analyst", "operations", "project manager",
]

TITLE_BLACKLIST = [
    "senior", "sr.", "lead", "director", "vp", "vice president",
    "head of", "chief", "principal", "staff product",
    "8+ years", "10+ years", "5+ years",
]

COMPANY_BLACKLIST: list[str] = []

# FastAPI server
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# Auth — override SECRET_KEY in production!
SECRET_KEY = os.getenv("SECRET_KEY", "7152bfd03c5e9022ea8ea60ff4b41a83c34f84088207ee1b5933acbfe5387117")
