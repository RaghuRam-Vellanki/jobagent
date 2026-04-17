from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    job_id = Column(String, index=True)
    platform = Column(String, default="linkedin")
    title = Column(String, default="")
    company = Column(String, default="")
    location = Column(String, default="")
    url = Column(String, default="")
    description = Column(Text, default="")

    match_score = Column(Float, default=0)
    ats_score = Column(Float, nullable=True)
    matched_kws = Column(Text, default="")
    ats_gaps = Column(Text, default="")

    status = Column(String, default="QUEUED")
    skip_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    response_status = Column(String, default="no_response")
    follow_up_date = Column(Date, nullable=True)

    discovered_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    date = Column(String, index=True)
    discovered = Column(Integer, default=0)
    queued = Column(Integer, default=0)
    approved = Column(Integer, default=0)
    applied = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    failed = Column(Integer, default=0)


class Profile(Base):
    __tablename__ = "profile"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True, index=True)
    full_name = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    city = Column(String, default="")
    state = Column(String, default="")
    country = Column(String, default="India")
    current_title = Column(String, default="")
    years_of_experience = Column(Integer, default=0)
    notice_period = Column(String, default="Immediate")
    expected_salary = Column(String, default="")
    portfolio_url = Column(String, default="")
    resume_path = Column(String, default="")
    cover_letter_template = Column(Text, default="")
    skills = Column(Text, default="")
    search_keywords = Column(Text, default="")
    location_filter = Column(String, default="India")
    experience_level = Column(String, default="entry_level,associate")
    job_type = Column(String, default="fulltime,internship")
    date_posted = Column(String, default="r86400")
    match_threshold = Column(Integer, default=60)
    daily_queue_limit = Column(Integer, default=50)
    daily_apply_limit = Column(Integer, default=25)
    delay_min = Column(Integer, default=4)
    delay_max = Column(Integer, default=10)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    platform = Column(String, index=True)
    email = Column(String, default="")
    password = Column(String, default="")
    session_cookies = Column(Text, nullable=True)
