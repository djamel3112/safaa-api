# ============================================================
# SAFAA API — FastAPI Server
# يربط Flutter بـ Python Core Engine
# شغّله بـ: uvicorn api:app --reload --port 8000
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import json, os

app = FastAPI(title="SAFAA API", version="1.0")

# السماح لـ Flutter بالاتصال
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# نسخ النواة مباشرة من safaa_core.py
# ============================================================

from enum import Enum
from dataclasses import dataclass

class State(Enum):
    CALM           = "calm"
    ALERT          = "alert"
    ELEVATED       = "elevated"
    OVERSTIMULATED = "overstimulated"
    DISTRACTED     = "distracted"
    SHUTDOWN       = "shutdown"

ACTIVITY_MATRIX = {
    State.CALM: {
        "path": "archery", "activity": "خريطة ذهنية تفاعلية",
        "guide": "شجعه. عزز ثقته. لا تكثر التوجيه.",
    },
    State.ALERT: {
        "path": "archery", "activity": "تحدي النقطة الواحدة",
        "guide": "تحدث بهدوء. لا ضغط.",
    },
    State.DISTRACTED: {
        "path": "archery", "activity": "لعبة 80/20",
        "guide": "دعه يختار. عزز قراره.",
    },
    State.ELEVATED: {
        "path": "swimming", "activity": "التلاشي البصري",
        "guide": "قلل الكلام. راقب التنفس.",
    },
    State.OVERSTIMULATED: {
        "path": "swimming", "activity": "التنفس المتزامن",
        "guide": "خفف الإضاءة. لا أوامر.",
    },
    State.SHUTDOWN: {
        "path": "swimming", "activity": "الوجود الصامت",
        "guide": "لا تتدخل. انتظر بصبر.",
    },
}

def apply_filter(raw_value: float, sensitivity: str) -> float:
    multipliers = {"low": 0.8, "medium": 1.0, "high": 1.3}
    return min(raw_value * multipliers.get(sensitivity, 1.0), 100)

def classify_state(filtered: float, father_input: str = None) -> State:
    if father_input:
        mapping = {
            "calm": State.CALM, "alert": State.ALERT,
            "elevated": State.ELEVATED,
            "overstimulated": State.OVERSTIMULATED,
            "distracted": State.DISTRACTED, "shutdown": State.SHUTDOWN,
        }
        if father_input.lower() in mapping:
            return mapping[father_input.lower()]
    if filtered <= 30:  return State.CALM
    elif filtered <= 55: return State.ALERT
    elif filtered <= 75: return State.ELEVATED
    else:                return State.OVERSTIMULATED

LOG_FILE = "safaa_sessions.json"

def log_session(data: dict):
    sessions = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            try: sessions = json.load(f)
            except: sessions = []
    sessions.append(data)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

# ============================================================
# Models — ما يرسله Flutter
# ============================================================

class SessionRequest(BaseModel):
    child_name:    str
    sensitivity:   str          # low | medium | high
    raw_value:     float        # 0-100
    sensor_type:   str = "mood" # movement | sound | mood | eye_contact
    father_input:  str = None   # calm | alert | elevated | ...

class SessionResponse(BaseModel):
    state:          str
    action:         str
    intensity:      int
    path:           str
    activity:       str
    guide:          str
    filtered_value: float
    warning:        str

# ============================================================
# Endpoints
# ============================================================

@app.get("/")
def root():
    return {"status": "SAFAA API running", "version": "1.0"}


@app.post("/session", response_model=SessionResponse)
def run_session(req: SessionRequest):
    # 1. Filter
    filtered = apply_filter(req.raw_value, req.sensitivity)

    # 2. Classify
    state = classify_state(filtered, req.father_input)

    # 3. Activity
    act = ACTIVITY_MATRIX[state]

    # 4. Intensity
    intensity_map = {
        State.CALM: 0, State.ALERT: 30, State.ELEVATED: 55,
        State.OVERSTIMULATED: 80, State.DISTRACTED: 20, State.SHUTDOWN: 0,
    }

    # 5. Log
    log_session({
        "timestamp":   datetime.now().isoformat(),
        "child_name":  req.child_name,
        "sensitivity": req.sensitivity,
        "raw_value":   req.raw_value,
        "sensor_type": req.sensor_type,
        "state":       state.value,
        "path":        act["path"],
        "activity":    act["activity"],
        "guide":       act["guide"],
        "intensity":   intensity_map[state],
    })

    return SessionResponse(
        state          = state.value,
        action         = act["path"],
        intensity      = intensity_map[state],
        path           = act["path"],
        activity       = act["activity"],
        guide          = act["guide"],
        filtered_value = round(filtered, 1),
        warning        = "تطبيق صفاء مساعد فقط — لا يُغني عن المختص",
    )


@app.get("/sessions/{child_name}")
def get_sessions(child_name: str):
    if not os.path.exists(LOG_FILE):
        return {"sessions": []}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try: all_sessions = json.load(f)
        except: return {"sessions": []}
    child_sessions = [
        s for s in all_sessions
        if s.get("child_name") == child_name
    ]
    return {"sessions": child_sessions}


@app.delete("/sessions/{child_name}")
def clear_sessions(child_name: str):
    if not os.path.exists(LOG_FILE):
        return {"deleted": 0}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try: all_sessions = json.load(f)
        except: return {"deleted": 0}
    kept    = [s for s in all_sessions if s.get("child_name") != child_name]
    deleted = len(all_sessions) - len(kept)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
    return {"deleted": deleted}
