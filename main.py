from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from datetime import date
import threading
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from database import engine, SessionLocal
from models import DailyEntry

# --------------------------------------------------
# App setup
# --------------------------------------------------

load_dotenv()

app = FastAPI(
    title="CalmNest API",
    description="Gentle screen-time guidance for children",
    version="1.0",
)

DailyEntry.__table__.create(bind=engine, checkfirst=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# OpenAI client
# --------------------------------------------------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------------------------------
# Simple in-memory notifier (safe for v1)
# --------------------------------------------------

history_updated = False

def notify_history_update():
    global history_updated
    history_updated = True

# --------------------------------------------------
# Models
# --------------------------------------------------

class DailyGuidanceRequest(BaseModel):
    age: int
    screen_minutes: int
    evening_usage: bool


class DailyGuidanceResponse(BaseModel):
    guidance: str


class HistoryItem(BaseModel):
    entry_date: date
    screen_minutes: int
    evening_usage: bool
    guidance: str


# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "CalmNest API running"}


@app.post("/daily-guidance", response_model=DailyGuidanceResponse)
def get_daily_guidance(data: DailyGuidanceRequest):
    """
    Instant baseline guidance.
    AI reflection runs asynchronously and updates History later.
    """

    quick_guidance = (
        "Some days naturally include more screen time than planned, and that’s okay. "
        "A calmer wind-down tomorrow evening may help your child settle more easily. "
        "You’re doing your best — small adjustments really do help."
    )

    # Save immediately
    db = SessionLocal()
    entry = DailyEntry(
        age=data.age,
        screen_minutes=data.screen_minutes,
        evening_usage=data.evening_usage,
        guidance=quick_guidance,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.close()

    # --------------------------------------------------
    # SMART SKIP RULES (AI runs more often)
    # --------------------------------------------------

    if data.screen_minutes < 30:
        return {"guidance": quick_guidance}

    if data.age <= 6 and data.screen_minutes < 60:
        return {"guidance": quick_guidance}

    if data.age > 6 and data.screen_minutes < 45:
        return {"guidance": quick_guidance}

    # --------------------------------------------------
    # Run AI asynchronously
    # --------------------------------------------------

    threading.Thread(
        target=generate_ai_guidance_async,
        args=(entry.id, data),
        daemon=True,
    ).start()

    return {"guidance": quick_guidance}


@app.get("/history", response_model=List[HistoryItem])
def get_history():
    db = SessionLocal()
    entries = (
        db.query(DailyEntry)
        .order_by(DailyEntry.entry_date.desc())
        .limit(7)
        .all()
    )
    db.close()
    return entries


# --------------------------------------------------
# 🔔 History auto-refresh stream (SSE)
# --------------------------------------------------

@app.get("/history/stream")
def history_stream():
    def event_generator():
        global history_updated
        while True:
            if history_updated:
                history_updated = False
                yield "data: updated\n\n"
            time.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# --------------------------------------------------
# Background AI worker
# --------------------------------------------------

def generate_ai_guidance_async(entry_id: int, data: DailyGuidanceRequest):
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=(
                f"Give gentle, non-judgmental parenting guidance for a "
                f"{data.age}-year-old child who had {data.screen_minutes} "
                f"minutes of screen time today. "
                f"Evening screen usage: {data.evening_usage}. "
                f"Tone: calm, reassuring, brief (3–4 sentences)."
            ),
        )

        ai_text = response.output_text

        db = SessionLocal()
        entry = db.query(DailyEntry).get(entry_id)

        if entry:
            entry.guidance = ai_text
            db.commit()
            notify_history_update()

        db.close()

    except Exception as e:
        print("AI background task failed:", e)
