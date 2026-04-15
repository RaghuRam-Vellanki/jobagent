import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, Profile, Credential

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Seed default profile if not exists
    db = SessionLocal()
    try:
        if not db.query(Profile).first():
            import json
            default_skills = [
                "product manager", "product owner", "product management", "apm",
                "prd", "user story", "acceptance criteria", "gherkin", "sprint",
                "backlog", "roadmap", "agile", "scrum", "jira", "confluence",
                "stakeholder", "lti", "saas", "edtech", "k12", "lms",
                "ux", "user research", "figma", "wireframe", "mvp",
                "sql", "analytics", "kpi", "okr", "go-to-market",
                "cross-functional", "a/b testing", "data-driven",
                "python", "notion", "miro", "power bi", "tableau",
                "competitive analysis", "market research", "prioritization",
            ]
            cover_letter = """Hi,

I'm Raghuram Vellanki, a Product Owner currently driving 0-to-1 development of a K12 SaaS LMS at Auzmor. I have hands-on experience writing modular PRDs, INVEST-compliant user stories with Gherkin acceptance criteria, leading sprint planning, design reviews in Figma, and managing LTI 1.3 integrations.

I'm deeply excited about this opportunity. My research rigor, execution focus, and ability to align cross-functional teams would allow me to contribute from day one.

Happy to connect!

Raghuram Vellanki
ramvellanki72@gmail.com | +91 62819 57658
linkedin.com/in/raghu-ram-vellanki-95134b248"""
            p = Profile(
                full_name="Raghuram Vellanki",
                email="ramvellanki72@gmail.com",
                phone="+916281957658",
                city="Hyderabad",
                state="Telangana",
                country="India",
                current_title="Product Owner",
                years_of_experience=1,
                notice_period="Immediate",
                expected_salary="600000",
                portfolio_url="vellanki-portfolio-builder.lovable.app",
                resume_path="resume/raghuram_vellanki_resume_v3.pdf",
                cover_letter_template=cover_letter,
                skills=json.dumps(default_skills),
                search_keywords="Product Manager,Product Owner,APM,Associate Product Manager",
                location_filter="India",
            )
            db.add(p)
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
