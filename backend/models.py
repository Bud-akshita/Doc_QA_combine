from database import Base
from sqlalchemy import Column, Integer, String, func , DateTime , ForeignKey, Text
from sqlalchemy.orm import relationship

class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer , primary_key = True , index = True)
    email = Column(String)
    password_hash = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Documents(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_name = Column(String, nullable=False) 
    doc_type = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    chat_history = relationship(
        "ChatHistory",
        back_populates="document",
        cascade="all, delete-orphan"
    )


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("Users", backref="chat_history")   # keep this for Users
    document = relationship("Documents", back_populates="chat_history")  # ✅ no backref here

# class smart_reminder(Base):
#     __tablename__ = "smart_reminder"

#     id = Column(Integer, Primary_key=True, index=True, autoincrement=True)
#     user_id = Column(Integer, ForeignKey("users.id"),nullable=False)
#     document_id = Column(Integer, ForeignKey("documnets.id"),nullable=False)
#     notify_days_before = Column(Integer, nullable = False)
#     event = Column(String, nullable=False)
#     event_status = Column(Boolean, default=True, nullable=False)