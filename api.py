# ============================================================
# SAFAA API v2.0 — FastAPI + SQLite
# الجلسات تُحفظ في قاعدة بيانات دائمة
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
import sqlite3, os

app = FastAPI(title="SAFAA API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Database
# ============================================================

DB = "safaa.db"

def init_db():
    con = sqlite3.connect(DB)
    con.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp     TEXT,
        child_name    TEXT,
        sensitivity   TEXT,
        raw_value     REAL,
        sensor_type   TEXT,
        state         TEXT,
        path          TEXT,
        activity      TEXT,
        guide         TEXT,
        intensity     INTEGER,
        filtered_value REAL
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS children (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE,
        sensitivity TEXT DEFAULT 'medium',
        created_at  TEXT
    )''')
    con.commit()
    con.close()

init_db()

# ============================================================
# Core Logic
# ============================================================

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

INTENSITY_MAP = {
    State.CALM: 0, State.ALERT: 30, State.ELEVATED: 55,
    State.OVERSTIMULATED: 80, State.DISTRACTED: 20, State.SHUTDOWN: 0,
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
    if filtered <= 30:   return State.CALM
    elif filtered <= 55: return State.ALERT
    elif filtered <= 75: return State.ELEVATED
    else:                return State.OVERSTIMULATED

# ============================================================
# Models
# ============================================================

class SessionRequest(BaseModel):
    child_name:   str
    sensitivity:  str
    raw_value:    float
    sensor_type:  str = "mood"
    father_input: str = None

class SessionResponse(BaseModel):
    state:          str
    action:         str
    intensity:      int
    path:           str
    activity:       str
    guide:          str
    filtered_value: float
    warning:        str

class ChildProfile(BaseModel):
    name:        str
    sensitivity: str = "medium"

# ============================================================
# Endpoints
# ============================================================

@app.get("/")
def root():
    return {"status": "SAFAA API running", "version": "2.0"}


# ---- تشغيل جلسة ----
@app.post("/session", response_model=SessionResponse)
def run_session(req: SessionRequest):
    filtered  = apply_filter(req.raw_value, req.sensitivity)
    state     = classify_state(filtered, req.father_input)
    act       = ACTIVITY_MATRIX[state]
    intensity = INTENSITY_MAP[state]

    # حفظ في SQLite
    con = sqlite3.connect(DB)
    con.execute('''INSERT INTO sessions
        (timestamp, child_name, sensitivity, raw_value,
         sensor_type, state, path, activity, guide,
         intensity, filtered_value)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
        datetime.now().isoformat(),
        req.child_name, req.sensitivity, req.raw_value,
        req.sensor_type, state.value, act["path"],
        act["activity"], act["guide"], intensity,
        round(filtered, 1),
    ))
    con.commit()
    con.close()

    return SessionResponse(
        state          = state.value,
        action         = act["path"],
        intensity      = intensity,
        path           = act["path"],
        activity       = act["activity"],
        guide          = act["guide"],
        filtered_value = round(filtered, 1),
        warning        = "تطبيق صفاء مساعد فقط — لا يُغني عن المختص",
    )


# ---- جلب الجلسات ----
@app.get("/sessions/{child_name}")
def get_sessions(child_name: str):
    con  = sqlite3.connect(DB)
    rows = con.execute(
        '''SELECT id, timestamp, child_name, sensitivity,
           raw_value, sensor_type, state, path,
           activity, guide, intensity, filtered_value
           FROM sessions WHERE child_name=?
           ORDER BY id DESC''',
        (child_name,)
    ).fetchall()
    con.close()
    cols = ['id','timestamp','child_name','sensitivity',
            'raw_value','sensor_type','state','path',
            'activity','guide','intensity','filtered_value']
    return {"sessions": [dict(zip(cols, r)) for r in rows]}


# ---- حفظ ملف الطفل ----
@app.post("/child")
def save_child(profile: ChildProfile):
    con = sqlite3.connect(DB)
    con.execute('''INSERT INTO children (name, sensitivity, created_at)
        VALUES (?,?,?)
        ON CONFLICT(name) DO UPDATE SET sensitivity=excluded.sensitivity''',
        (profile.name, profile.sensitivity, datetime.now().isoformat())
    )
    con.commit()
    con.close()
    return {"status": "saved", "name": profile.name}


# ---- جلب ملف الطفل ----
@app.get("/child/{name}")
def get_child(name: str):
    con = sqlite3.connect(DB)
    row = con.execute(
        'SELECT name, sensitivity, created_at FROM children WHERE name=?',
        (name,)
    ).fetchone()
    con.close()
    if row:
        return {"found": True, "name": row[0],
                "sensitivity": row[1], "created_at": row[2]}
    return {"found": False}


# ---- حذف ملف الطفل (تسجيل الخروج) ----
@app.delete("/child/{name}")
def delete_child(name: str):
    con = sqlite3.connect(DB)
    con.execute('DELETE FROM children WHERE name=?', (name,))
    con.commit()
    con.close()
    return {"status": "logged_out", "name": name}


# ---- حذف الجلسات ----
@app.delete("/sessions/{child_name}")
def clear_sessions(child_name: str):
    con = sqlite3.connect(DB)
    cur = con.execute(
        'DELETE FROM sessions WHERE child_name=?', (child_name,))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return {"deleted": deleted}
