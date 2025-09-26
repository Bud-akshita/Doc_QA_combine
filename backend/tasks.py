import smtplib
from email.mime.text import MIMEText
from celery_app import celery_app
import os
from dotenv import load_dotenv
from celery.result import AsyncResult
from celery.exceptions import Ignore

celery_app.control.purge()

load_dotenv()

@celery_app.task
def send_email(subject, body, to_email):
    print(f"Starting email task...")

    try:
        # Sender email setup
        from_email = os.getenv("email")
        password = os.getenv("pass")
        
        print(f"From email: {from_email}")
        
        if not from_email or not password:
            print(" Error: Email credentials not found")
            return f"Error: Email credentials not found in .env file"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        print(" Connecting to Gmail SMTP...")
        # Connect to Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(from_email, password)
            print("Sending email...")
            server.sendmail(from_email, to_email, msg.as_string())

        print(" Email sent successfully!")
        return f"Email sent successfully to {to_email}"
    
    except Exception as e:
        print(f" Error occurred: {str(e)}")
        return f"Failed to send email: {str(e)}"
    
def cancel_scheduled_email(task_id: str):
    """Cancel a scheduled email task"""
    try:
        # Revoke task (whether scheduled, reserved, or active)
        celery_app.control.revoke(task_id, terminate=True)

        # Check status
        res = AsyncResult(task_id, app=celery_app)

        if res.status in ["REVOKED", "PENDING"]:
            return {
                "status": "success",
                "task_id": task_id,
                "message": "Email reminder cancellation requested"
            }
        else:
            return {
                "status": "warning",
                "task_id": task_id,
                "message": f"Task revoke requested but current state = {res.status}"
            }

    except Exception as e:
        return {"status": "error", "message": str(e), "task_id": task_id}