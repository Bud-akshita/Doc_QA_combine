import os
import smtplib
from email.mime.text import MIMEText
import json
import time
import redis

REDIS_URL = os.environ.get("REDIS_URL")
r = redis.from_url(REDIS_URL)

EMAIL_QUEUE = "email_queue"

def send_email_task(task):
    subject = task.get("subject")
    body = task.get("body")
    to_email = task.get("to_email")

    try:
        from_email = os.environ.get("email")
        password = os.environ.get("pass")

        if not from_email or not password:
            print("Error: Email credentials not found")
            return

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        print(f"Sending email to {to_email}...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())

        print(f"Email sent successfully to {to_email}")

    except Exception as e:
        print(f"Failed to send email: {str(e)}")

def process_email_queue():
    """
    Process Redis queue:
    - Only send emails whose send_timestamp <= current time
    - Push back tasks not yet due
    """
    current_ts = time.time()
    tasks_to_keep = []

    all_tasks = r.lrange(EMAIL_QUEUE, 0, -1)

    for task_json in all_tasks:
        task = json.loads(task_json)
        print(task)
        send_ts = task.get("send_timestamp", 0)

        if send_ts <= current_ts:
            send_email_task(task)
            r.lrem(EMAIL_QUEUE, 1, task_json)  # remove from queue after sending
        else:
            tasks_to_keep.append(task_json)  # not ready yet

# if __name__ == "__main__":
#     print("Email scheduler started...")
#     while True:
#         process_email_queue()
#         time.sleep(10)  # check every 10 seconds
