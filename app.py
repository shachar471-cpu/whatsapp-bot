from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
import csv
import os
from datetime import datetime

app = Flask(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LEADS_FILE = "leads.csv"
sessions = {}

SYSTEM_PROMPT = """
אתה נציג מכירות חכם של Magic Travel Tours.
תענה בעברית, קצר, ברור, נעים ומכירתי.
המטרה שלך:
1. לעזור ללקוח לגבי חופשה
2. לשאול רק שאלה אחת בכל פעם
3. לא לחפור
4. לשמור על תחושה אנושית
5. אם חסר מידע חשוב, תשאל שאלה ממוקדת

מידע חשוב שצריך לאסוף בהדרגה:
- יעד
- תאריכים או חודש
- כמות נוסעים
- תקציב
- שם
- טלפון

כללים:
- אם הלקוח שואל שאלה כללית, תענה קצר ואז תמשיך לשאלה הבאה
- אם הלקוח כבר נתן מידע, אל תשאל שוב אותו דבר
- אל תמציא מחירים או זמינות
- אחרי שיש את כל הפרטים, תגיד שקיבלנו את הפרטים וששחר או נציג יחזרו אליו בהקדם
"""

QUESTIONS = [
    ("destination", "לאן בא לך לטוס? ✈️"),
    ("dates", "לאילו תאריכים או חודש בערך חשבת? 📅"),
    ("travelers", "כמה אנשים טסים? 👨‍👩‍👧‍👦"),
    ("budget", "מה התקציב בערך? 💰"),
    ("name", "מה השם שלך? 😊"),
    ("phone", "אפשר מספר טלפון לחזרה? 📞"),
]

DONE_MESSAGE = "מעולה, קיבלתי את כל הפרטים שלך ✅\nשחר או נציג מטעמנו יחזרו אליך בהקדם עם אופציות מדויקות ✈️"

WELCOME_MESSAGE = """היי 👋
ברוך הבא ל-Magic Travel Tours ✈️

אני כאן כדי לעזור לך למצוא חופשה מדויקת 😎
נתחיל בכמה שאלות קצרות.

לאן בא לך לטוס? ✍️"""

def normalize_text(text: str) -> str:
    return (text or "").strip()

def ensure_csv_exists():
    if not os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "created_at",
                "whatsapp_number",
                "destination",
                "dates",
                "travelers",
                "budget",
                "name",
                "phone"
            ])

def save_lead(lead: dict):
    ensure_csv_exists()
    with open(LEADS_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            lead.get("from_number", ""),
            lead.get("destination", ""),
            lead.get("dates", ""),
            lead.get("travelers", ""),
            lead.get("budget", ""),
            lead.get("name", ""),
            lead.get("phone", ""),
        ])

def looks_like_phone(text: str) -> bool:
    digits = "".join(ch for ch in text if ch.isdigit())
    return 8 <= len(digits) <= 15

def extract_obvious_fields(state: dict, incoming: str):
    txt = incoming.strip()
    low = txt.lower()

    if "תאילנד" in txt or txt in ["1", "1️⃣"]:
        state["destination"] = "תאילנד"
    elif "דובאי" in txt or txt in ["2", "2️⃣"]:
        state["destination"] = "דובאי"
    elif "אירופה" in txt or txt in ["3", "3️⃣"]:
        state["destination"] = "אירופה"
    elif "ארה" in txt or txt in ["4", "4️⃣"] or "usa" in low:
        state["destination"] = "ארה״ב"

    if looks_like_phone(txt):
        state["phone"] = txt

def next_missing_field(state: dict):
    for field, question in QUESTIONS:
        if not state.get(field):
            return field, question
    return None, None

def ask_gpt(user_message: str, state: dict, next_question: str) -> str:
    if not OPENAI_API_KEY:
        return next_question

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    state_summary = (
        f"פרטים שכבר קיימים:\n"
        f"יעד: {state.get('destination','')}\n"
        f"תאריכים: {state.get('dates','')}\n"
        f"נוסעים: {state.get('travelers','')}\n"
        f"תקציב: {state.get('budget','')}\n"
        f"שם: {state.get('name','')}\n"
        f"טלפון: {state.get('phone','')}\n"
        f"\nהשאלה הבאה שצריך לשאול: {next_question}"
    )

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": state_summary},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.5
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"].strip()
        return reply or next_question
    except Exception:
        return next_question

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = normalize_text(request.form.get("Body", ""))
    from_number = request.form.get("From", "")

    resp = MessagingResponse()
    msg = resp.message()

    state = sessions.get(from_number, {"step": "active", "from_number": from_number})

    if incoming_msg.lower() in ["reset", "restart", "איפוס", "התחל מחדש"]:
        state = {"step": "active", "from_number": from_number}
        sessions[from_number] = state
        msg.body(WELCOME_MESSAGE)
        return str(resp)

    if not state.get("started"):
        state["started"] = True
        sessions[from_number] = state
        msg.body(WELCOME_MESSAGE)
        return str(resp)

    extract_obvious_fields(state, incoming_msg)

    # Save current message into the next missing field if it's not already inferred
    field, question = next_missing_field(state)
    if field:
        if field == "destination" and not state.get("destination"):
            state["destination"] = incoming_msg
        elif field == "dates" and not state.get("dates"):
            state["dates"] = incoming_msg
        elif field == "travelers" and not state.get("travelers"):
            state["travelers"] = incoming_msg
        elif field == "budget" and not state.get("budget"):
            state["budget"] = incoming_msg
        elif field == "name" and not state.get("name") and not looks_like_phone(incoming_msg):
            state["name"] = incoming_msg
        elif field == "phone" and not state.get("phone"):
            state["phone"] = incoming_msg

    next_field, next_question = next_missing_field(state)

    if not next_field:
        save_lead(state)
        state["done"] = True
        sessions[from_number] = state
        msg.body(DONE_MESSAGE)
        return str(resp)

    sessions[from_number] = state
    reply = ask_gpt(incoming_msg, state, next_question)
    msg.body(reply)
    return str(resp)

@app.route("/", methods=["GET"])
def home():
    return "Smart bot is running!"

@app.route("/health", methods=["GET"])
def health():
    return {"ok": True}
