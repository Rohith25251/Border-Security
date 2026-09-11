"""
Main entry point for IBVAP FastAPI Application.
Run with:
    python main.py
or
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import uvicorn
from api.app import app

if __name__ == "__main__":
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)
