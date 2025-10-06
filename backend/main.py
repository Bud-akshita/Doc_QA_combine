from fastapi import FastAPI, status, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import models
from database import engine, SessionLocal, db_dependency
from typing import Annotated
import auth
import docs
import website
from auth import get_current_user
from schedular import process_email_queue
import threading

app = FastAPI()

def scheduler_loop():
    while True:
        process_email_queue()
        time.sleep(60)

@app.on_event("startup")
def start_scheduler():
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://doc-qa-frontend-347720367133.asia-south1.run.app"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)

app.include_router(auth.router)
app.include_router(docs.router)
app.include_router(website.router)
# app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")

models.Base.metadata.create_all(bind=engine)

user_dependency = Annotated[dict, Depends(get_current_user)]

@app.get("/api/hello")
def read_root():
    return {"message": "Hello from FastAPI + React on GCP!"}

@app.get("/", status_code=status.HTTP_200_OK)
async def user(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')
    return {"User": user}
