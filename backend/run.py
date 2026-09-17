import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=int(os.getenv("COPILOT_PORT", "8080")),
        access_log=False,
    )
