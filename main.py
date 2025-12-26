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

    # 1️⃣ Generate guidance (example text for now)
    guidance_text = (
        "Some days naturally include more screen time, and that’s okay. "
        "A calmer wind-down tomorrow evening may help your child settle more easily."
        "You’re doing your best, and small adjustments really do help."
    )

    # 2️⃣ SAVE ENTRY TO DATABASE  ✅ THIS IS THE PART YOU ASKED ABOUT
    db = SessionLocal()
    entry = DailyEntry(
        age=data.age,
        screen_minutes=data.screen_minutes,
        evening_usage=data.evening_usage,
        guidance=guidance_text,
    )
    db.add(entry)
    db.commit()
    db.close()

    # 3️⃣ Return response to frontend
    return {
        "guidance": guidance_text
    }
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

