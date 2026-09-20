from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    
    # Profile
    age = Column(Integer)
    gender = Column(String)
    height_cm = Column(Float)
    weight_kg = Column(Float)
    activity_level = Column(String)
    medical_conditions = Column(JSON, default=list)
    
    # Goals
    goal_type = Column(String)
    target_calories = Column(Integer, nullable=True)
    
    # Preferences
    diet_type = Column(String)
    cuisine_preference = Column(String)
    allergies = Column(JSON, default=list)
    dislikes = Column(JSON, default=list)

    meal_plans = relationship("MealPlan", back_populates="user")
    recommendations = relationship("Recommendation", back_populates="user")

class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_data = Column(JSON) # Stores the JSON schema matched payload
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="meal_plans")

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    recommendation_data = Column(JSON) # Stores list of recommendations
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="recommendations")


class MealPhotoLog(Base):
    """A photo-derived meal analysis. `confirmed` flips to 1 once the user has
    checked the estimated portions, so unreviewed estimates stay distinguishable
    from reviewed ones."""
    __tablename__ = "meal_photo_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    analysis = Column(JSON)
    confirmed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class CallSchedule(Base):
    """When the app may contact the user. Everything defaults to off, and
    voice calls additionally require consent_to_call."""
    __tablename__ = "call_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    phone = Column(String, nullable=True)
    consent_to_call = Column(Integer, default=0)
    schedule = Column(JSON, default=list)
    updated_at = Column(DateTime, default=datetime.utcnow)


class DailyLog(Base):
    """One row per user per day. `entries` is append-only through the day and
    is what makes the plan dynamic -- every voice call, text and photo lands
    here and the next recommendation is recomputed from it."""
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    log_date = Column(String, index=True)
    entries = Column(JSON, default=list)
    summary = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class GameState(Base):
    """Streaks, XP and shields. Persisted rather than held in memory: a
    streak that silently resets on restart destroys the mechanic's value."""
    __tablename__ = "game_states"

    id = Column(Integer, primary_key=True, index=True)
    user_key = Column(String, index=True, unique=True)
    state = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Squad(Base):
    """A small accountability group; combined streaks are computed on read."""
    __tablename__ = "squads"

    id = Column(Integer, primary_key=True, index=True)
    squad_id = Column(String, index=True, unique=True)
    name = Column(String, nullable=True)
    member_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    """A chat thread. Messages are stored on the row so a session loads in one
    query; volumes here are small (a person's own conversations)."""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, unique=True)
    user_id = Column(Integer, index=True, default=1)
    title = Column(String, default="New chat")
    agent = Column(String, default="general")
    messages = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    """
    Every agent output, kept.

    Plans, assessments and progress reports were previously visible only in
    the chat bubble that produced them, so nothing could be revisited or
    referenced by the voice agent. One row per run; the newest of a given
    agent is treated as current.
    """
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    agent = Column(String, index=True)
    payload = Column(JSON)          # what the agent was asked
    result = Column(JSON)           # what it produced
    created_at = Column(DateTime, default=datetime.utcnow)
