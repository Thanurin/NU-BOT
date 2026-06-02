import os
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, request

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

API = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)
USERS_FILE = "users.json"


# ======================
# DB
# ======================
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)


def load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(data):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ======================
# SEND HELPERS
# ======================
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    requests.post(API + "/sendMessage", json=payload)


def send_photo(chat_id, file_id, caption=None, reply_markup=None):
    payload = {"chat_id": chat_id, "photo": file_id}

    if caption:
        payload["caption"] = caption

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    requests.post(API + "/sendPhoto", json=payload)


def send_video(chat_id, file_id, caption=None):
    payload = {
        "chat_id": chat_id,
        "video": file_id
    }

    if caption:
        payload["caption"] = caption

    requests.post(API + "/sendVideo", json=payload)


def send_document(chat_id, file_id, caption=None):
    payload = {
        "chat_id": chat_id,
        "document": file_id
    }

    if caption:
        payload["caption"] = caption

    requests.post(API + "/sendDocument", json=payload)


# ======================
# PLAN CHECK
# ======================
def has_active_plan(user_id):
    users = load_users()
    uid = str(user_id)

    if uid not in users:
        return False

    expiry = users[uid].get("expiry")
    if not expiry:
        return False

    return datetime.now() < datetime.fromisoformat(expiry)


# ======================
# HOME
# ======================
@app.route("/", methods=["GET"])
def home():
    return "BOT RUNNING"


# ======================
# WEBHOOK
# ======================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "OK"

    users = load_users()

    # ======================
    # IGNORE DUPLICATE UPDATES (IMPORTANT FIX)
    # ======================
    update_id = data.get("update_id")
    if update_id:
        if "seen_updates" not in users:
            users["seen_updates"] = []

        if update_id in users["seen_updates"]:
            return "OK"

        users["seen_updates"].append(update_id)
        users["seen_updates"] = users["seen_updates"][-200:]
        save_users(users)

    # ======================
    # GROUP CONNECT EVENT
    # ======================
    if "my_chat_member" in data:
        member = data["my_chat_member"]
        chat = member["chat"]

        chat_id = chat["id"]
        chat_type = chat["type"]

        from_user = member["from"]["id"]
        new_status = member["new_chat_member"]["status"]

        if chat_type in ["group", "supergroup"]:
            if new_status in ["administrator", "member"]:

                uid = str(from_user)

                if uid not in users:
                    users[uid] = {}

                users[uid]["group_id"] = chat_id
                save_users(users)

                send_message(from_user, "✅ Bot connected successfully")
                send_message(chat_id, "✅ Bot connected successfully")

        return "OK"

    # ======================
    # CALLBACK QUERY
    # ======================
    if "callback_query" in data:
        cq = data["callback_query"]
        cb_data = cq["data"]

        if cb_data.startswith("approve:"):
            _, user_id, plan = cb_data.split(":")

            uid = str(user_id)

            # ❌ prevent double approval spam
            if users.get(uid, {}).get("approved"):
                send_message(ADMIN_ID, "⚠️ Already approved")
                return "OK"

            now = datetime.now()

            if plan == "week":
                expiry = now + timedelta(days=7)
            elif plan == "month":
                expiry = now + timedelta(days=30)
            elif plan == "year":
                expiry = now + timedelta(days=365)
            else:
                send_message(ADMIN_ID, "❌ Invalid plan")
                return "OK"

            if uid not in users:
                users[uid] = {}

            users[uid]["expiry"] = expiry.isoformat()
            users[uid]["approved"] = True

            save_users(users)

            send_message(user_id, f"✅ Approved!\nPlan: {plan}")
            send_message(ADMIN_ID, f"✅ User {user_id} approved")

        return "OK"

    # ======================
    # MESSAGE
    # ======================
    if "message" not in data:
        return "OK"

    msg = data["message"]

    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"]["type"]

    text = msg.get("text", "")

    # ======================
    # IGNORE SERVICE MESSAGES
    # ======================
    if "new_chat_members" in msg or "left_chat_member" in msg:
        return "OK"

    # ======================
    # START
    # ======================
    if text == "/start":
        send_message(chat_id, "🇰🇭 សួស្តី!\n\n👉 /buy")
        return "OK"

    # ======================
    # BUY
    # ======================
    if text == "/buy":
        with open("qr.png", "rb") as f:
            requests.post(
                API + "/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption":
                        "💳 PREMIUM PLANS\n\n"
                        "🥉 WEEK PLAN\n💲 3$ / week\n\n"
                        "🥈 MONTH PLAN\n💲 11.5$ / month\n\n"
                        "🥇 YEAR PLAN\n💲 120$ / year\n\n"
                        "📸 Send screenshot after payment"
                },
                files={"photo": f}
            )
        return "OK"

    # ======================
    # PAYMENT SCREENSHOT
    # ======================
    if "photo" in msg:
        file_id = msg["photo"][-1]["file_id"]
        caption = msg.get("caption", "")

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Week", "callback_data": f"approve:{user_id}:week"},
                    {"text": "Month", "callback_data": f"approve:{user_id}:month"}
                ],
                [
                    {"text": "Year", "callback_data": f"approve:{user_id}:year"}
                ]
            ]
        }

        send_message(
            ADMIN_ID,
            f"📸 Payment from {user_id}",
            reply_markup=keyboard
        )

        send_photo(ADMIN_ID, file_id, caption=caption)
        return "OK"

    # ======================
    # PLAN CHECK
    # ======================
    if not has_active_plan(user_id):
        send_message(user_id, "❌ Plan expired\n👉 Use /buy")
        return "OK"

    # ======================
    # GET GROUP
    # ======================
    user_data = users.get(str(user_id), {})
    group_id = user_data.get("group_id")

    if not group_id:
        return "OK"

    # ======================
    # ONLY PRIVATE CHAT FORWARDING
    # ======================
    if chat_type != "private":
        return "OK"

    # ======================
    # FORWARD CONTENT (WITH CAPTION FIX)
    # ======================
    if text:
        send_message(group_id, text)

    elif "video" in msg:
        send_video(group_id, msg["video"]["file_id"], msg.get("caption", ""))

    elif "document" in msg:
        send_document(group_id, msg["document"]["file_id"], msg.get("caption", ""))

    return "OK"


# ======================
# RUN
# ======================
if __name__ == "__main__":
    if WEBHOOK_URL:
        requests.get(f"{API}/setWebhook?url={WEBHOOK_URL}/webhook")

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
