<div align="center">

# VAce QuizMaster

**A full-stack quiz management platform built with Flask, PostgreSQL, and deployed on Vercel.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![Deployed on Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-000000?style=flat-square&logo=vercel&logoColor=white)](https://vishal-mad1.vercel.app)
[![Tests](https://img.shields.io/badge/Tests-42%20passing-22c55e?style=flat-square&logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

[Live Demo](https://vishal-mad1.vercel.app) · [Report a Bug](https://github.com/Vish2BDev/quizmaster-v2/issues) · [Request a Feature](https://github.com/Vish2BDev/quizmaster-v2/issues)

</div>

---

## Overview

VAce QuizMaster is a role-based quiz management system built as part of the Modern Application Development (MAD 1) coursework. It allows administrators to create and manage subjects, chapters, quizzes, and questions, while students can take timed quizzes and track their score history across all subjects.

**Admin capabilities:**
- Create and manage the full subject → chapter → quiz → question hierarchy
- Manage user accounts with role-based permissions
- View analytics: score distributions, monthly activity trends, top performers
- Export user data to CSV

**Student capabilities:**
- Browse all available quizzes grouped by subject and chapter
- Take timed quizzes with a live countdown
- View complete score history with pagination

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.0.3, Flask-Login, Flask-WTF |
| ORM | SQLAlchemy 2.0, Flask-SQLAlchemy 3.1.1 |
| Database | PostgreSQL (Supabase) / SQLite (local dev) |
| Auth | Werkzeug password hashing (bcrypt), CSRF protection |
| Frontend | Jinja2, Bootstrap 5, Chart.js |
| Deployment | Vercel (serverless) |
| Testing | pytest, 42 tests across 7 test classes |

---

## Architecture

```
VAce QuizMaster
├── app.py                   Flask application factory (create_app)
├── config.py                Dev / Prod / Test configuration classes
├── requirements.txt         Pinned dependencies
├── vercel.json              Serverless deployment descriptor
│
├── api/
│   └── index.py             Vercel WSGI entry point + lazy DB init
│
├── controllers/
│   └── controllers.py       All routes (~1,100 lines, monolithic by design)
│
├── models/
│   ├── database.py          SQLAlchemy instance
│   └── models.py            ORM models: User, Subject, Chapter, Quiz,
│                            Question, Option, Score
│
├── static/
│   └── css/style.css        Application stylesheet
│
├── templates/
│   ├── base.html            Root layout (CSRF meta tag, JS injection)
│   ├── admin/               15 admin templates
│   ├── auth/                login.html, register.html
│   ├── errors/              403, 404, 500 error pages
│   ├── partials/            Flash messages, pagination component
│   └── user/                Dashboard, quiz attempt, score history
│
└── tests/
    ├── conftest.py          Pre-import DB URI injection (isolated SQLite)
    └── test_app.py          42 tests across 7 classes
```

### Data Model

```
User ──────────────────── Score
 │                           │
 │              Subject ─── Chapter ─── Quiz ─── Question ─── Option
 │                                        │
 └────────────────────────────────────────┘
```

| Model | Key Fields |
|-------|-----------|
| `User` | id, username, full_name, password_hash, dob, role (admin/user) |
| `Subject` | id, name, description |
| `Chapter` | id, subject_id FK, name, description |
| `Quiz` | id, chapter_id FK, name, date_of_quiz, time_duration |
| `Question` | id, quiz_id FK, question_statement |
| `Option` | id, question_id FK, option_text, is_correct |
| `Score` | id, quiz_id FK, user_id FK, total_scored, total_possible |

---

## Getting Started

### Prerequisites

- Python 3.12+
- pip

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/Vish2BDev/quizmaster-v2.git
cd quizmaster-v2

# 2. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables (copy the example)
cp .env.example .env
# Edit .env — set SECRET_KEY, leave DATABASE_URL empty to use SQLite

# 5. Run the app
python app.py
```

The app will start at `http://localhost:5000`.  
On first run, the database is initialised automatically and a default admin account is created:

```
Username: admin
Password: admin123   ← change this immediately
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes (production) | Cryptographically random string for session signing |
| `DATABASE_URL` | No (optional) | PostgreSQL connection string. Falls back to SQLite locally |
| `FLASK_DEBUG` | No | Set to `true` to enable debug mode |

Generate a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Deployment (Vercel + Supabase)

This app is configured for serverless deployment on Vercel with Supabase as a persistent PostgreSQL backend.

### 1. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Go to **Settings → Database → Connect → Transaction pooler** (port 6543)
3. Copy the connection URI and replace `[YOUR-PASSWORD]` with your database password

### 2. Deploy to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Link or create a project
vercel link

# Set production secrets
python -c "import secrets; print(secrets.token_hex(32))" | vercel env add SECRET_KEY production
# Then paste your Supabase URI:
vercel env add DATABASE_URL production

# Deploy
vercel --prod
```

On the first request after deployment, the app automatically creates all database tables and the default admin account.

> **Note:** Vercel's free tier (Hobby plan) uses ephemeral serverless functions. Do not use SQLite in production — it will be wiped between requests. Always set `DATABASE_URL` to a hosted PostgreSQL instance.

---

## Testing

The test suite covers authentication, RBAC, admin CRUD, user quiz workflow, and edge cases.

```bash
# Run all tests
pytest tests/test_app.py -v -p no:flask
```

```
====================== 42 passed, 52 warnings in ~12s ======================
```

| Test Class | Count | Coverage |
|------------|-------|----------|
| `TestAuthentication` | 10 | Login, logout, registration, wrong password, duplicate users, invalid DOB, short passwords |
| `TestRBAC` | 5 | Unauthenticated access, admin-only routes, cross-role restrictions |
| `TestAdminSubjects` | 5 | List, create, duplicate detection, empty name, search |
| `TestAdminUsers` | 5 | List, create, short password, invalid role, CSV export |
| `TestAdminQuizzes` | 2 | List quizzes, list questions with filter |
| `TestUserWorkflow` | 6 | Dashboard, quiz GET, all-correct submit, zero-score submit, history, 404 |
| `TestEdgeCases` | 9 | Home redirect, 404 page, invalid quiz, self-delete block, search empty |

> The `-p no:flask` flag disables `pytest-flask` (which uses a removed Flask 2.x internal API) in favour of manual fixture-based context management.

---

## Security

This project was put through a full security audit. Key hardening applied:

| Finding | Severity | Status |
|---------|----------|--------|
| Open redirect on login `?next=` (CWE-601) | Critical | ✅ Fixed |
| No CSRF protection on any form | High | ✅ Fixed — Flask-WTF CSRFProtect |
| Logout via GET (CSRF log-off attack) | High | ✅ Fixed — POST-only logout |
| Admin password reset on every restart | High | ✅ Fixed — create-only logic |
| Hardcoded `SECRET_KEY` | High | ✅ Fixed — env var with warning |
| No server-side password length validation | Medium | ✅ Fixed — min 8 chars |

Session cookies are configured with `Secure`, `HttpOnly`, and `SameSite=Lax` in production.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest tests/test_app.py -v -p no:flask`
5. Open a pull request against `main`

Please ensure all 42 tests pass before opening a PR.

---

## Roadmap

- [ ] **Blueprint refactor** — split `controllers.py` into `auth/`, `admin/`, `user/` blueprints
- [ ] **Flask-Migrate** — Alembic-based migrations for zero-downtime schema changes
- [ ] **Rate limiting** — Flask-Limiter on login and quiz submission endpoints
- [ ] **Server-side quiz timer** — store deadline in DB to prevent client-side cheating
- [ ] **Email validation** — add email field to User model for password recovery
- [ ] **Fix deprecations** — replace `Query.get()` with `db.session.get()`, `utcnow()` with `datetime.now(timezone.utc)`

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">
Built by <a href="https://github.com/Vish2BDev">Vishal Bhandari</a> · MAD 1 Project · 2026
</div>
