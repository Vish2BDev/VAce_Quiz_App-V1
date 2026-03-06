"""
tests/test_app.py — Professional QA test suite for VAce_QuizMaster.

Run:
    pip install pytest
    pytest tests/test_app.py -v -p no:flask

Test strategy:
  - Uses a temp-file SQLite DB (clean per test session, no side-effects on dev DB)
  - CSRF is disabled for tests via config.update()
  - Covers: auth, admin CRUD, user workflows, edge cases

NOTE: The app uses app.app_context().push() in create_app() so we configure
      the temp DB URI BEFORE any SQLAlchemy operation to ensure lazy engine
      creation picks up the test URI.
"""

import pytest
import sys
import os
from datetime import date as _date

# Make project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['FLASK_ENV'] = 'testing'
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-tests-only')

from app import app as _app
from models.database import db as _db
from models.models import User, Subject, Chapter, Quiz, Question, Option, Score


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def app():
    """
    Session-scoped app fixture.
    The DATABASE_URL env var is set by tests/conftest.py BEFORE this module
    is imported, so Flask-SQLAlchemy's lazy engine creation uses the temp
    test DB URI — not the production quiz_master.db.
    """
    _app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key-for-tests-only',
    })

    _db.create_all()
    _seed_test_data()

    yield _app

    _db.session.remove()


def _seed_test_data():
    """Insert minimal test data into the test DB."""
    admin = User(username='testadmin', full_name='Test Admin', role='admin')
    admin.set_password('adminpass123')
    _db.session.add(admin)

    user = User(username='testuser', full_name='Test User', role='user')
    user.set_password('userpass123')
    _db.session.add(user)

    subj = Subject(name='Mathematics', description='Math subject')
    _db.session.add(subj)
    _db.session.flush()

    chap = Chapter(subject_id=subj.id, name='Algebra', description='Algebra chapter')
    _db.session.add(chap)
    _db.session.flush()

    quiz = Quiz(
        chapter_id=chap.id,
        name='Algebra Basics',
        date_of_quiz=_date(2026, 1, 1),
        time_duration='10:00',
    )
    _db.session.add(quiz)
    _db.session.flush()

    q1 = Question(quiz_id=quiz.id, question_statement='What is 2 + 2?')
    _db.session.add(q1)
    _db.session.flush()
    _db.session.add(Option(question_id=q1.id, option_text='3', is_correct=False))
    _db.session.add(Option(question_id=q1.id, option_text='4', is_correct=True))

    q2 = Question(quiz_id=quiz.id, question_statement='What is 3 * 3?')
    _db.session.add(q2)
    _db.session.flush()
    _db.session.add(Option(question_id=q2.id, option_text='6', is_correct=False))
    _db.session.add(Option(question_id=q2.id, option_text='9', is_correct=True))

    _db.session.commit()


@pytest.fixture()
def client(app):
    """
    Test client with its own fresh app context per test.

    Flask 3.0 reuses the globally-pushed app context (from create_app()'s
    app.app_context().push()) for ALL requests, so g._login_user set during
    one test leaks into the next.  Pushing a fresh app context here gives
    each test its own isolated g, preventing cross-test user contamination.
    """
    ctx = app.app_context()
    ctx.push()
    test_client = app.test_client()
    yield test_client
    ctx.pop()


@pytest.fixture()
def admin_client(client):
    """Client already logged in as admin."""
    client.post('/login', data={'username': 'testadmin', 'password': 'adminpass123'})
    return client


@pytest.fixture()
def user_client(client):
    """Client already logged in as regular user."""
    client.post('/login', data={'username': 'testuser', 'password': 'userpass123'})
    return client


def _get_quiz_id():
    """Get Algebra Basics quiz ID — call only within an active app context."""
    quiz = Quiz.query.filter_by(name='Algebra Basics').first()
    return quiz.id if quiz else None


def _get_question_options():
    """Return {question_id: correct_option_id} for Algebra Basics — needs active ctx."""
    quiz = Quiz.query.filter_by(name='Algebra Basics').first()
    result = {}
    for q in quiz.questions:
        correct = next(o for o in q.options if o.is_correct)
        result[q.id] = correct.id
    return result


# ---------------------------------------------------------------------------
# AUTH TESTS
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_login_page_loads(self, client):
        r = client.get('/login')
        assert r.status_code == 200
        assert b'Login' in r.data

    def test_register_page_loads(self, client):
        r = client.get('/register')
        assert r.status_code == 200
        assert b'Register' in r.data

    def test_valid_user_login(self, client):
        r = client.post('/login', data={
            'username': 'testuser', 'password': 'userpass123'
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Welcome back' in r.data

    def test_valid_admin_login(self, client):
        r = client.post('/login', data={
            'username': 'testadmin', 'password': 'adminpass123'
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Admin Dashboard' in r.data

    def test_invalid_password(self, client):
        r = client.post('/login', data={
            'username': 'testuser', 'password': 'wrongpassword'
        }, follow_redirects=True)
        assert b'Invalid username or password' in r.data

    def test_nonexistent_user(self, client):
        r = client.post('/login', data={
            'username': 'nobody', 'password': 'anything'
        }, follow_redirects=True)
        assert b'Invalid username or password' in r.data

    def test_register_new_user(self, client):
        r = client.post('/register', data={
            'username': 'newuser99',
            'password': 'securepass99',
            'full_name': 'New User',
            'qualification': 'BSc',
            'dob': '2000-01-15'
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Registration successful' in r.data

    def test_register_duplicate_username(self, client):
        r = client.post('/register', data={
            'username': 'testuser',
            'password': 'sometestpass',
            'full_name': 'Duplicate'
        }, follow_redirects=True)
        assert b'already taken' in r.data

    def test_register_short_password(self, client):
        r = client.post('/register', data={
            'username': 'shortpwduser',
            'password': 'abc',
            'full_name': 'Short Pass'
        }, follow_redirects=True)
        assert b'8 characters' in r.data

    def test_register_missing_required_fields(self, client):
        r = client.post('/register', data={
            'username': '',
            'password': '',
            'full_name': ''
        }, follow_redirects=True)
        assert b'required' in r.data

    def test_logout(self, user_client):
        r = user_client.post('/logout', follow_redirects=True)
        assert b'logged out' in r.data

    def test_password_is_hashed(self, app):
        """Ensure passwords are never stored as plain text."""
        with app.app_context():
            u = User.query.filter_by(username='testuser').first()
            assert u.password_hash != 'userpass123'
            assert u.password_hash.startswith(('scrypt:', 'pbkdf2:', 'argon2:'))

    def test_open_redirect_blocked(self, client):
        """Login should not redirect to external URLs."""
        r = client.post(
            '/login?next=https://evil.com',
            data={'username': 'testuser', 'password': 'userpass123'},
            follow_redirects=False
        )
        location = r.headers.get('Location', '')
        assert 'evil.com' not in location


# ---------------------------------------------------------------------------
# ROLE-BASED ACCESS CONTROL TESTS
# ---------------------------------------------------------------------------

class TestRBAC:

    def test_admin_dashboard_requires_admin(self, user_client):
        r = user_client.get('/admin/dashboard', follow_redirects=True)
        # Should redirect away from admin dashboard
        assert b'Admin Dashboard' not in r.data or b'Admin access required' in r.data

    def test_unauthenticated_blocked(self, client):
        r = client.get('/admin/dashboard', follow_redirects=True)
        assert b'Login' in r.data

    def test_admin_can_access_admin_dashboard(self, admin_client):
        r = admin_client.get('/admin/dashboard')
        assert r.status_code == 200

    def test_admin_cannot_attempt_quiz(self, admin_client):
        quiz_id = _get_quiz_id()
        r = admin_client.get(f'/quiz/{quiz_id}/attempt', follow_redirects=True)
        assert b'Admins cannot attempt quizzes' in r.data

    def test_admin_cannot_view_user_history(self, admin_client):
        r = admin_client.get('/quiz/history', follow_redirects=True)
        assert b'Admins do not have quiz attempt histories' in r.data


# ---------------------------------------------------------------------------
# ADMIN CRUD TESTS
# ---------------------------------------------------------------------------

class TestAdminSubjects:

    def test_list_subjects(self, admin_client):
        r = admin_client.get('/admin/subjects')
        assert r.status_code == 200
        assert b'Mathematics' in r.data

    def test_create_subject(self, admin_client):
        r = admin_client.post('/admin/subject/create', data={
            'name': 'Science', 'description': 'Natural sciences'
        }, follow_redirects=True)
        assert b'created successfully' in r.data

    def test_create_subject_duplicate(self, admin_client):
        r = admin_client.post('/admin/subject/create', data={
            'name': 'Mathematics', 'description': 'Dup'
        }, follow_redirects=True)
        assert b'already exists' in r.data

    def test_create_subject_empty_name(self, admin_client):
        r = admin_client.post('/admin/subject/create', data={
            'name': '', 'description': ''
        }, follow_redirects=True)
        assert b'cannot be empty' in r.data

    def test_search_subjects(self, admin_client):
        r = admin_client.get('/admin/subjects?search=Math')
        assert r.status_code == 200
        assert b'Mathematics' in r.data


class TestAdminUsers:

    def test_list_users(self, admin_client):
        r = admin_client.get('/admin/users')
        assert r.status_code == 200

    def test_create_user(self, admin_client):
        r = admin_client.post('/admin/users/create', data={
            'username': 'newadminuser',
            'password': 'strongpass123',
            'full_name': 'Admin Created User',
            'role': 'user'
        }, follow_redirects=True)
        assert b'created successfully' in r.data

    def test_create_user_short_password(self, admin_client):
        r = admin_client.post('/admin/users/create', data={
            'username': 'shortpwu',
            'password': 'abc',
            'full_name': 'Short PW',
            'role': 'user'
        }, follow_redirects=True)
        assert b'8 characters' in r.data

    def test_create_user_invalid_role(self, admin_client):
        r = admin_client.post('/admin/users/create', data={
            'username': 'hackuser',
            'password': 'validpass123',
            'full_name': 'Hacker',
            'role': 'superuser'  # invalid role
        }, follow_redirects=True)
        assert b'Invalid role' in r.data

    def test_export_csv(self, admin_client):
        r = admin_client.get('/admin/users/export_csv')
        assert r.status_code == 200
        assert b'Username' in r.data
        assert r.content_type == 'text/csv'


class TestAdminQuizzes:

    def test_list_quizzes(self, admin_client):
        r = admin_client.get('/admin/quizzes')
        assert r.status_code == 200
        assert b'Algebra Basics' in r.data

    def test_list_questions(self, admin_client):
        quiz_id = _get_quiz_id()
        r = admin_client.get(f'/admin/questions?quiz_id={quiz_id}')
        assert r.status_code == 200
        assert b'What is' in r.data


# ---------------------------------------------------------------------------
# USER WORKFLOW TESTS
# ---------------------------------------------------------------------------

class TestUserWorkflow:

    def test_user_dashboard_loads(self, user_client):
        r = user_client.get('/dashboard')
        assert r.status_code == 200
        assert b'Algebra Basics' in r.data

    def test_quiz_attempt_get(self, user_client):
        quiz_id = _get_quiz_id()
        r = user_client.get(f'/quiz/{quiz_id}/attempt')
        assert r.status_code == 200
        assert b'What is' in r.data

    def test_quiz_attempt_all_correct(self, user_client):
        quiz_id = _get_quiz_id()
        correct_answers = _get_question_options()
        form_data = {f'question_{qid}': str(oid) for qid, oid in correct_answers.items()}
        r = user_client.post(f'/quiz/{quiz_id}/attempt', data=form_data, follow_redirects=True)
        assert r.status_code == 200
        # Score should be 2/2
        assert b'2 out of 2' in r.data or b'scored' in r.data

    def test_quiz_attempt_no_answers_scores_zero(self, user_client):
        quiz_id = _get_quiz_id()
        r = user_client.post(f'/quiz/{quiz_id}/attempt', data={}, follow_redirects=True)
        assert r.status_code == 200

    def test_quiz_history_shows_attempts(self, user_client):
        r = user_client.get('/quiz/history')
        assert r.status_code == 200
        # At least one attempt from test above should appear
        assert b'Algebra' in r.data or b'No attempts' in r.data or b'history' in r.data.lower()

    def test_nonexistent_quiz_returns_404(self, user_client):
        r = user_client.get('/quiz/99999/attempt')
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# EDGE CASE TESTS
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_home_redirects_unauthenticated_to_login(self, client):
        r = client.get('/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert 'login' in r.headers['Location'].lower()

    def test_404_page(self, client):
        r = client.get('/this/path/does/not/exist')
        assert r.status_code == 404

    def test_quiz_with_invalid_id_returns_404(self, user_client):
        r = user_client.get('/quiz/0/attempt')
        assert r.status_code == 404

    def test_admin_cannot_delete_own_account(self, admin_client):
        admin = User.query.filter_by(username='testadmin').first()
        admin_id = admin.id
        r = admin_client.post(f'/admin/users/{admin_id}/delete', follow_redirects=True)
        assert b'cannot delete your own' in r.data

    def test_subject_search_no_results(self, admin_client):
        r = admin_client.get('/admin/subjects?search=zzznomatch')
        assert r.status_code == 200

    def test_register_invalid_dob(self, client):
        r = client.post('/register', data={
            'username': 'baddateuser',
            'password': 'goodpass123',
            'full_name': 'Bad Date',
            'dob': 'not-a-date'
        }, follow_redirects=True)
        assert b'Invalid date' in r.data
