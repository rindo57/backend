import os
from dotenv import load_dotenv

# Load .env file from the same directory as this script
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Backward compatibility for existing imports.
GEMINI_API_KEY = OPENROUTER_API_KEY
FIREBASE_KEY_PATH = os.path.join(os.path.dirname(__file__), "firebase-key.json")
TTS_API_KEY = os.environ.get("TTS_API_KEY", "")
