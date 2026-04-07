# -*- coding: utf-8 -*-
import csv
import os
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

LEADS_FILE = "leads.csv"
sessions = {}

WELCOME_MESSAGE = "היי 👋\nברוך הבא ל-Magic Travel ✈️\n\nאני הסוכן האישי שלך 😎\nלאן בא לך לטוס?\n1️⃣ תאילנד\n2️⃣ דובאי\n3️⃣ אירופה\n4️⃣ ארה״ב"

ASK_TRAVELERS = "כמה אנשים טסים?"
ASK_NAME = "מה השם שלך?"
ASK_PHONE = "מה הטלפון שלך?"
DONE_MESSAGE = "מעולה! נחזור אליך בקרוב ✈️"

def normalize(text):
    return (text or "").strip()

def save_lead(data):
    file_exists = os.path.exists(LEADS_FILE)
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["time","number","destination","people","name","phone"])
        writer.writerow(data)

@app.route("/webhook", methods=["POST"])
def webhook():
    msg_in = normalize(request.form.get("Body"))
    user = request.form.get("From")

    resp = MessagingResponse()
    msg = resp.message()

    state = sessions.get(user, {"step": "start"})

    if state["step"] == "start":
        msg.body(WELCOME_MESSAGE)
        state["step"] = "destination"

    elif state["step"] == "destination":
        state["destination"] = msg_in
        state["step"] = "people"
        msg.body(ASK_TRAVELERS)

    elif state["step"] == "people":
        state["people"] = msg_in
        state["step"] = "name"
        msg.body(ASK_NAME)

    elif state["step"] == "name":
        state["name"] = msg_in
        state["step"] = "phone"
        msg.body(ASK_PHONE)

    elif state["step"] == "phone":
        state["phone"] = msg_in
        save_lead([datetime.now(), user, state["destination"], state["people"], state["name"], state["phone"]])
        msg.body(DONE_MESSAGE)
        state["step"] = "done"

    sessions[user] = state
    return str(resp)

@app.route("/health")
def health():
    return {"ok": True}
