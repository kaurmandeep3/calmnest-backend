from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, SessionLocal
from models import DailyEntry
from typing import List
from pydantic import BaseModel
from datetime import date
import threading
from typing import Optional



# Load environment variables
load_dotenv()

# Initialize app
app = FastAPI(
    title="Calm Screen Companion API",
    description="Gentle screen-time guidance for children aged 3–6",
    version="1.0"
)
DailyEntry.__table__.create(bind=engine, checkfirst=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
print(os.getenv("OPENAI_API_KEY"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Request model
class DailyGuidanceRequest(BaseModel):
    age: int
    screen_minutes: int
    evening_usage: bool

# Response model
class DailyGuidanceResponse(BaseModel):
    guidance: str

class HistoryItem(BaseModel):
    entry_date: date
    screen_minutes: int
    evening_usage: bool
    guidance: str


@app.post("/daily-guidance")
def get_daily_guidance(data: DailyGuidanceRequest):

    # 1️⃣ Instant, calm baseline guidance
    quick_guidance = (
        "Some days naturally include more screen time than planned, and that’s okay. "
        "A calmer wind-down tomorrow evening may help your child settle more easily. "
        "You’re doing your best — small adjustments really do help."
    )

    # 2️⃣ Save immediately
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

    if data.age <= 6 and data.screen_minutes < 60:
        return {"guidance": quick_guidance}
    
    # 3️⃣ Run OpenAI in background (non-blocking)
    threading.Thread(
        target=generate_ai_guidance_async,
        args=(entry.id, data),
        daemon=True,
    ).start()

    # 4️⃣ Respond instantly
    return {"guidance": quick_guidance}
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

        db.close()

    except Exception as e:
        print("AI background task failed:", e)
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

