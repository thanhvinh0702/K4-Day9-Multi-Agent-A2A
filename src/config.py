import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-mini"

DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input" / "input"
OUTPUT_DIR = ROOT_DIR / "output"
TRACE_PATH = ROOT_DIR / "logging" / "trace.jsonl"
METADATA_PATH = ROOT_DIR / "logging" / "metadata.json"
