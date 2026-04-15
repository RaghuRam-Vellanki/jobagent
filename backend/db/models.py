from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, index=True)
    platform = Column(String, default="linkedin")  # linkedin | naukri | internshala | unstop
    title = Column(String, default="")
    company = Column(String, default="")
    location = Column(String, default="")
    url = Column(String, default="")
    description = Column(Text, default="")

    # Scoring
    match_score = Column(Float, default=0)
    ats_score = Column(Float, nullable=True)
    matched_kws = Column(Text, default="")   # comma-joined
    ats_gaps = Column(Text, default="")      # comma-joined missing keywords

    # Workflow
    status = Column(String, default="QUEUED")  # QUEUED | APPROVED | APPLIED | SKIPPED | FAILED | DUPLICATE
    skip_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Application tracking
    response_status = Column(String, default="no_response")  # no_response | viewed | interview | rejected | offer
    follow_up_date = Column(Date, nullable=True)

    # Timestamps
    discovered_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True)
    date = Column(String, unique=True, index=True)
    discovered = Column(Integer, default=0)
    queued = Column(Integer, default=0)
    approved = Column(Integer, default=0)
    applied = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    failed = Column(Integer, default=0)


class Profile(Base):
    __tablename__ = "profile"

    id = Column(Integer, primary_key=True)
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
    skills = Column(Text, default="")           # JSON array string
    search_keywords = Column(Text, default="")  # comma-joined
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
    platform = Column(String, unique=True, index=True)
    email = Column(String, default="")
    password = Column(String, default="")
    session_cookies = Column(Text, nullable=True)  # JSON string
