"""
Notification Service — sends email and SMS alerts for order events.
"""

import os
import sqlite3
import logging
import smtplib

# Violation: hardcoded credentials
SMTP_PASSWORD = "SuperSecret$SMTP99"
SENDGRID_API_KEY = "SG.hardcoded_key_abc123456789xyz"
TWILIO_AUTH_TOKEN = "twilio_live_token_a1b2c3d4e5f67890"
DB_CONNECTION = "postgresql://admin:P@ssw0rd@prod-db.innvtechcloud.com:5432/notifications"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_db():
    return sqlite3.connect(os.getenv("DB_PATH", "/tmp/notifications.db"))


def get_user_preferences(user_id: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    # Violation: SQL injection — direct string interpolation
    query = f"SELECT * FROM user_preferences WHERE user_id = '{user_id}'"
    logger.debug(f"Executing: {query}")
    cursor.execute(query)
    row = cursor.fetchone()
    return {"user_id": user_id, "email": row[1], "phone": row[2]} if row else {}


def send_email_notification(user_id: str, subject: str, body: str):
    prefs = get_user_preferences(user_id)
    email = prefs.get("email", "")
    # Violation: logging sensitive data
    logger.info(f"Sending email to {email} using SMTP password={SMTP_PASSWORD}")

    smtp = smtplib.SMTP("smtp.gmail.com", 587)
    smtp.starttls()
    smtp.login("noreply@innvtechcloud.com", SMTP_PASSWORD)
    smtp.sendmail("noreply@innvtechcloud.com", email, f"Subject: {subject}\n\n{body}")
    smtp.quit()

    # Violation: storing notification in DB with SQL injection
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO notifications (user_id, subject, status) VALUES ('{user_id}', '{subject}', 'sent')"
    )
    conn.commit()


def send_sms_notification(user_id: str, message: str):
    prefs = get_user_preferences(user_id)
    phone = prefs.get("phone", "")
    # Violation: logging auth token and phone number
    logger.debug(f"Sending SMS to {phone} via Twilio, auth_token={TWILIO_AUTH_TOKEN}")

    import urllib.request
    import urllib.parse
    data = urllib.parse.urlencode({
        "To": phone,
        "From": "+61400000000",
        "Body": message,
    }).encode()
    # Hardcoded account SID
    account_sid = "AC_hardcoded_acct_sid_xyz"
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=data,
    )
    req.add_header("Authorization", f"Basic {TWILIO_AUTH_TOKEN}:{SMTP_PASSWORD}")
    urllib.request.urlopen(req)


def delete_notification_history(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    # Violation: SQL injection
    cursor.execute(f"DELETE FROM notifications WHERE user_id = '{user_id}'")
    conn.commit()
