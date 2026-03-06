import os
import csv
import io
import logging
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlparse, urljoin

from flask import render_template, request, redirect, url_for, flash, abort, current_app as app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract, or_
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models.database import db
from models.models import User, Subject, Chapter, Quiz, Question, Option, Score

logger = logging.getLogger(__name__)

# Setup Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- SAFE REDIRECT HELPER ---
def is_safe_redirect_url(target):
    """Prevent open-redirect: only allow redirects to same host."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ('http', 'https')
        and ref_url.netloc == test_url.netloc
    )


# --- ADMIN REQUIRED DECORATOR ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Admin access required for this page.", "danger")
            if current_user.is_authenticated:
                return redirect(url_for('dashboard_user'))
            else:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- UTILITY: CREATE DEFAULT ADMIN (only on first run) ---
def create_update_default_admin():
    """
    Creates the default admin ONLY if no admin user exists yet.
    NEVER overwrites an existing admin's password — admins manage
    their own credentials after first login.
    Default credentials: admin / admin123  — CHANGE IMMEDIATELY.
    """
    admin_user = User.query.filter_by(username='admin').first()

    if not admin_user:
        admin_user = User(
            username='admin',
            full_name='VAce Admin',
            role='admin'
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        logger.warning(
            "Default admin created with password 'admin123'. "
            "CHANGE THIS PASSWORD IMMEDIATELY via Admin → Users."
        )
        print("[SECURITY] Default admin created. Change password 'admin123' immediately!")
    else:
        logger.info("Default admin already exists — skipping creation.")

# --- UTILITY: DATABASE INITIALIZATION ---
def init_db():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Creating/Updating default admin user...")
        create_update_default_admin()
        print("Database initialization complete.")

# --- ROUTES ---

# Home route
@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('dashboard_admin'))
        return redirect(url_for('dashboard_user'))
    return redirect(url_for('login'))

# Make datetime available in templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow, 'today_date': date.today().isoformat()}

# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            logger.info("User '%s' logged in.", user.username)
            flash(f'Welcome back, {user.full_name}!', 'success')
            # Security: validate next_page to prevent open-redirect attacks
            next_page = request.args.get('next')
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for('dashboard_admin')) if user.role == 'admin' else redirect(url_for('dashboard_user'))
        else:
            logger.warning("Failed login attempt for username '%s'.", username or '<empty>')
            flash('Invalid username or password. Please try again.', 'danger')

    return render_template('auth/login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logger.info("User '%s' logged out.", current_user.username)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
         return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        qualification = request.form.get('qualification')
        dob_str = request.form.get('dob')  # Format: YYYY-MM-DD

        if not username or not password or not full_name:
             flash('Username, Password, and Full Name are required.', 'warning')
             return render_template('auth/register.html', username=username, full_name=full_name, qualification=qualification, dob=dob_str)

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'warning')
            return render_template('auth/register.html', username=username, full_name=full_name, qualification=qualification, dob=dob_str)

        if len(username) > 100 or len(full_name) > 150:
            flash('Username or Full Name is too long.', 'warning')
            return render_template('auth/register.html', username=username, full_name=full_name, qualification=qualification, dob=dob_str)

        dob_obj = None
        if dob_str:
            try:
                dob_obj = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format for DOB. Use YYYY-MM-DD.', 'warning')
                return render_template('auth/register.html', username=username, full_name=full_name, qualification=qualification, dob=dob_str)

        existing_user = User.query.filter(func.lower(User.username) == func.lower(username)).first()
        if existing_user:
            flash('Username already taken. Please choose another.', 'warning')
            return render_template('auth/register.html', username=username, full_name=full_name, qualification=qualification, dob=dob_str)
        else:
            new_user = User(
                username=username,
                full_name=full_name,
                qualification=qualification,
                dob=dob_obj,
                role='user'
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('auth/register.html')

# --- ADMIN ROUTES ---

@app.route('/admin/dashboard')
@login_required
@admin_required
def dashboard_admin():
    subject_count = Subject.query.count()
    user_count = User.query.filter(User.role == 'user').count()
    quiz_count = Quiz.query.count()
    latest_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    latest_quizzes = Quiz.query.order_by(Quiz.created_at.desc()).limit(5).all()

    return render_template(
        'admin/admin_dashboard.html',
        subject_count=subject_count,
        user_count=user_count,
        quiz_count=quiz_count,
        latest_users=latest_users,
        latest_quizzes=latest_quizzes
    )

# Subjects routes
@app.route('/admin/subjects', methods=['GET'])
@login_required
@admin_required
def subjects_list():
    search_query = request.args.get('search', '').strip()
    query = Subject.query
    if search_query:
        query = query.filter(Subject.name.ilike(f'%{search_query}%'))
    subjects = query.order_by(Subject.name).all()
    return render_template('admin/admin_subjects.html', subjects=subjects, search_query=search_query)

@app.route('/admin/subject/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_subject():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Subject name cannot be empty.', 'warning')
            return render_template('admin/admin_create_subject.html', subject_name=name, description=description)

        existing_subj = Subject.query.filter(func.lower(Subject.name) == func.lower(name)).first()
        if existing_subj:
            flash('Subject with this name already exists.', 'warning')
            return render_template('admin/admin_create_subject.html', subject_name=name, description=description)
        else:
            try:
                subject = Subject(name=name, description=description)
                db.session.add(subject)
                db.session.commit()
                flash('Subject created successfully.', 'success')
                return redirect(url_for('subjects_list'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating subject: {e}', 'danger')
                return render_template('admin/admin_create_subject.html', subject_name=name, description=description)
    return render_template('admin/admin_create_subject.html')

@app.route('/admin/subject/<int:subject_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def subject_edit(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        new_description = request.form.get('description', '').strip()

        if not new_name:
            flash('Subject name cannot be empty.', 'warning')
            return render_template('admin/admin_edit_subject.html', subject=subject)

        existing_subj = Subject.query.filter(
            func.lower(Subject.name) == func.lower(new_name),
            Subject.id != subject_id
        ).first()
        if existing_subj:
            flash('Another subject with this name already exists.', 'warning')
            return render_template('admin/admin_edit_subject.html', subject=subject)

        try:
            subject.name = new_name
            subject.description = new_description
            db.session.commit()
            flash("Subject updated successfully.", "success")
            return redirect(url_for('subjects_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating subject: {e}', 'danger')
            return render_template('admin/admin_edit_subject.html', subject=subject)
    return render_template('admin/admin_edit_subject.html', subject=subject)

@app.route('/admin/subject/<int:subject_id>/delete', methods=['POST'])
@login_required
@admin_required
def subject_delete(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    try:
        db.session.delete(subject)
        db.session.commit()
        flash(f'Subject "{subject.name}" deleted.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting subject "{subject.name}": {e}. Make sure related items (chapters, quizzes) are handled.', 'danger')
    return redirect(url_for('subjects_list'))

# Chapters routes
@app.route('/admin/chapters', methods=['GET'])
@login_required
@admin_required
def chapters_list():
    chapters = Chapter.query.join(Chapter.subject).options(
        db.joinedload(Chapter.subject)
    ).order_by(Subject.name, Chapter.name).all()
    return render_template('admin/admin_chapters.html', chapters=chapters)

@app.route('/admin/chapter/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_chapter():
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        submitted_data = {'chapter_name': name, 'description': description, 'preselected_subject_id': subject_id}

        if not subject_id or not name:
            flash('Subject and Chapter Name are required.', 'warning')
            subjects = Subject.query.order_by(Subject.name).all()
            return render_template('admin/admin_create_chapter.html', subjects=subjects, **submitted_data)

        try:
            subject = Subject.query.get(int(subject_id))
            if not subject:
                flash('Invalid Subject selected.', 'danger')
                subjects = Subject.query.order_by(Subject.name).all()
                return render_template('admin/admin_create_chapter.html', subjects=subjects, **submitted_data)

            chapter = Chapter(subject_id=int(subject_id), name=name, description=description)
            db.session.add(chapter)
            db.session.commit()
            flash('Chapter created successfully.', 'success')
            return redirect(url_for('chapters_list'))
        except ValueError:
            flash('Invalid Subject ID format.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating chapter: {e}', 'danger')

        subjects = Subject.query.order_by(Subject.name).all()
        return render_template('admin/admin_create_chapter.html', subjects=subjects, **submitted_data)

    subjects = Subject.query.order_by(Subject.name).all()
    preselected_subject_id = request.args.get('subject_id', type=int)
    return render_template('admin/admin_create_chapter.html',
                           subjects=subjects,
                           preselected_subject_id=preselected_subject_id)

@app.route('/admin/chapter/<int:chapter_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def chapter_edit(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    subjects = Subject.query.order_by(Subject.name).all()

    if request.method == 'POST':
        new_subject_id = request.form.get('subject_id')
        new_name = request.form.get('name', '').strip()
        new_description = request.form.get('description', '').strip()

        if not new_subject_id or not new_name:
            flash('Subject and Chapter Name are required.', 'warning')
            return render_template('admin/admin_edit_chapter.html', chapter=chapter, subjects=subjects)

        try:
            subject = Subject.query.get(int(new_subject_id))
            if not subject:
                flash('Invalid Subject selected.', 'danger')
                return render_template('admin/admin_edit_chapter.html', chapter=chapter, subjects=subjects)

            chapter.subject_id = int(new_subject_id)
            chapter.name = new_name
            chapter.description = new_description
            db.session.commit()
            flash("Chapter updated successfully.", "success")
            return redirect(url_for('chapters_list'))
        except ValueError:
            flash('Invalid Subject ID format.', 'danger')
            return render_template('admin/admin_edit_chapter.html', chapter=chapter, subjects=subjects)
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating chapter: {e}', 'danger')
            return render_template('admin/admin_edit_chapter.html', chapter=chapter, subjects=subjects)

    return render_template('admin/admin_edit_chapter.html', chapter=chapter, subjects=subjects)

@app.route('/admin/chapter/<int:chapter_id>/delete', methods=['POST'])
@login_required
@admin_required
def chapter_delete(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    try:
        db.session.delete(chapter)
        db.session.commit()
        flash(f'Chapter "{chapter.name}" deleted.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting chapter "{chapter.name}": {e}. Make sure related quizzes are handled.', 'danger')
    return redirect(url_for('chapters_list'))

# Quizzes routes
@app.route('/admin/quizzes', methods=['GET'])
@login_required
@admin_required
def quizzes_list():
    search_query = request.args.get('search', '').strip()
    query = Quiz.query.options(db.joinedload(Quiz.chapter).joinedload(Chapter.subject))
    if search_query:
        search_term = f'%{search_query}%'
        query = query.join(Quiz.chapter).join(Chapter.subject).filter(
            or_(
                Quiz.name.ilike(search_term),
                Chapter.name.ilike(search_term),
                Subject.name.ilike(search_term)
            )
        )
    quizzes = query.order_by(Quiz.date_of_quiz.desc(), Quiz.name).all()
    return render_template('admin/admin_quizzes.html',
                           quizzes=quizzes,
                           search_query=search_query)

@app.route('/admin/quiz/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_quiz():
    if request.method == 'POST':
        chapter_id = request.form.get('chapter_id')
        quiz_name = request.form.get('quiz_name', '').strip()
        date_of_quiz_str = request.form.get('date_of_quiz')
        time_duration = request.form.get('time_duration', '').strip()
        remarks = request.form.get('remarks', '').strip()

        submitted_data = {
            'quiz_name': quiz_name, 'date_of_quiz': date_of_quiz_str,
            'time_duration': time_duration, 'remarks': remarks,
            'preselected_chapter_id': chapter_id
        }

        if not chapter_id or not quiz_name or not date_of_quiz_str or not time_duration:
            flash('Chapter, Quiz Name, Date, and Duration (MM:SS) are required.', 'warning')
            chapters = Chapter.query.join(Chapter.subject).options(db.joinedload(Chapter.subject)).order_by(Subject.name, Chapter.name).all()
            return render_template('admin/admin_create_quiz.html', chapters=chapters, **submitted_data)
        else:
            try:
                date_of_quiz = datetime.strptime(date_of_quiz_str, '%Y-%m-%d').date()
                if len(time_duration.split(':')) != 2 or not all(part.isdigit() for part in time_duration.split(':')):
                    raise ValueError("Invalid duration format. Use MM:SS")

                chapter = Chapter.query.get(int(chapter_id))
                if not chapter:
                    flash('Invalid Chapter selected.', 'danger')
                    raise ValueError("Invalid chapter")

                quiz = Quiz(
                    chapter_id=int(chapter_id),
                    name=quiz_name,
                    date_of_quiz=date_of_quiz,
                    time_duration=time_duration,
                    remarks=remarks
                )
                db.session.add(quiz)
                db.session.commit()
                flash('Quiz created successfully.', 'success')
                return redirect(url_for('quizzes_list'))
            except ValueError as e:
                flash(f'Invalid input: {e}. Check date format (YYYY-MM-DD), duration format (MM:SS), or chapter ID.', 'warning')
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating quiz: {e}', 'danger')

            chapters = Chapter.query.join(Chapter.subject).options(db.joinedload(Chapter.subject)).order_by(Subject.name, Chapter.name).all()
            return render_template('admin/admin_create_quiz.html', chapters=chapters, **submitted_data)

    chapters = Chapter.query.join(Chapter.subject).options(
        db.joinedload(Chapter.subject)
    ).order_by(Subject.name, Chapter.name).all()
    return render_template('admin/admin_create_quiz.html', chapters=chapters)

@app.route('/admin/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def quiz_edit(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    chapters = Chapter.query.join(Chapter.subject).options(
        db.joinedload(Chapter.subject)
    ).order_by(Subject.name, Chapter.name).all()

    if request.method == 'POST':
        new_chapter_id = request.form.get('chapter_id')
        new_name = request.form.get('name', '').strip()
        date_str = request.form.get('date_of_quiz')
        new_duration = request.form.get('time_duration', '').strip()
        new_remarks = request.form.get('remarks', '').strip()

        if not new_chapter_id or not new_name or not date_str or not new_duration:
            flash('Chapter, Quiz Name, Date, and Duration (MM:SS) are required.', 'warning')
            quiz.date_of_quiz_str = date_str
            return render_template('admin/admin_edit_quiz.html', quiz=quiz, chapters=chapters)

        try:
            new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if len(new_duration.split(':')) != 2 or not all(part.isdigit() for part in new_duration.split(':')):
                raise ValueError("Invalid duration format. Use MM:SS")

            chapter = Chapter.query.get(int(new_chapter_id))
            if not chapter:
                flash('Invalid Chapter selected.', 'danger')
                raise ValueError("Invalid chapter")

            quiz.chapter_id = int(new_chapter_id)
            quiz.name = new_name
            quiz.date_of_quiz = new_date
            quiz.time_duration = new_duration
            quiz.remarks = new_remarks
            db.session.commit()
            flash("Quiz updated successfully.", "success")
            return redirect(url_for('quizzes_list'))
        except ValueError as e:
            flash(f'Invalid input: {e}. Check date format (YYYY-MM-DD), duration format (MM:SS), or chapter ID.', 'warning')
            quiz.date_of_quiz_str = date_str
            return render_template('admin/admin_edit_quiz.html', quiz=quiz, chapters=chapters)
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating quiz: {e}', 'danger')
            quiz.date_of_quiz_str = date_str
            return render_template('admin/admin_edit_quiz.html', quiz=quiz, chapters=chapters)

    quiz.date_of_quiz_str = quiz.date_of_quiz.strftime('%Y-%m-%d')
    return render_template('admin/admin_edit_quiz.html', quiz=quiz, chapters=chapters)

@app.route('/admin/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
@admin_required
def quiz_delete(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    quiz_name = quiz.name
    try:
        db.session.delete(quiz)
        db.session.commit()
        flash(f'Quiz "{quiz_name}" deleted.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting quiz "{quiz_name}": {e}.', 'danger')
    return redirect(url_for('quizzes_list'))

# Questions routes
@app.route('/admin/questions')
@login_required
@admin_required
def questions_list():
    quiz_id_filter = request.args.get('quiz_id', type=int)
    query = Question.query.options(db.joinedload(Question.quiz).joinedload(Quiz.chapter).joinedload(Chapter.subject))
    quiz_filter_name = None
    if quiz_id_filter:
        quiz_for_filter = Quiz.query.get(quiz_id_filter)
        if quiz_for_filter:
            query = query.filter(Question.quiz_id == quiz_id_filter)
            quiz_filter_name = quiz_for_filter.name
        else:
            flash(f"Quiz with ID {quiz_id_filter} not found for filtering.", "warning")
            quiz_id_filter = None
    questions = query.order_by(Question.quiz_id, Question.id).all()
    quizzes = Quiz.query.join(Quiz.chapter).join(Chapter.subject).options(db.joinedload(Quiz.chapter).joinedload(Chapter.subject)).order_by(Subject.name, Chapter.name, Quiz.name).all()

    return render_template(
        'admin/admin_questions.html',
        questions=questions,
        quizzes=quizzes,
        quiz_id_filter=quiz_id_filter,
        quiz_filter_name=quiz_filter_name
    )

@app.route('/admin/quiz/<int:quiz_id>/question/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if request.method == 'POST':
        question_statement = request.form.get('question_statement', '').strip()
        options_texts = request.form.getlist('option_text[]')
        correct_option_index_str = request.form.get('correct_option')

        submitted_data = {'question_statement': question_statement, 'options_texts': options_texts, 'correct_option_index_str': correct_option_index_str}

        if not question_statement:
            flash('Question statement cannot be empty.', 'warning')
            return render_template('admin/admin_create_question.html', quiz=quiz, **submitted_data)

        valid_options = [(i, text.strip()) for i, text in enumerate(options_texts) if text.strip()]
        if len(valid_options) < 2:
            flash('Please provide at least two non-empty options.', 'warning')
            return render_template('admin/admin_create_question.html', quiz=quiz, **submitted_data)

        if correct_option_index_str is None:
            flash('Please mark one option as correct.', 'warning')
            return render_template('admin/admin_create_question.html', quiz=quiz, **submitted_data)

        try:
            correct_option_index = int(correct_option_index_str)
            if not any(idx == correct_option_index for idx, text in valid_options):
                flash('The selected correct option must not be empty.', 'warning')
                raise ValueError("Correct option is empty")
        except ValueError:
            flash('Invalid correct option selected or the option was empty.', 'danger')
            return render_template('admin/admin_create_question.html', quiz=quiz, **submitted_data)

        try:
            new_question = Question(
                quiz_id=quiz.id,
                question_statement=question_statement
            )
            db.session.add(new_question)
            db.session.flush()

            for i, text in valid_options:
                is_correct = (i == correct_option_index)
                new_opt = Option(
                    question_id=new_question.id,
                    option_text=text,
                    is_correct=is_correct
                )
                db.session.add(new_opt)

            db.session.commit()
            flash("Question created successfully!", "success")
            return redirect(url_for('questions_list', quiz_id=quiz.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating question: {e}", "danger")
            return render_template('admin/admin_create_question.html', quiz=quiz, **submitted_data)

    return render_template('admin/admin_create_question.html', quiz=quiz)

@app.route('/admin/question/<int:question_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def question_edit(question_id):
    question = Question.query.options(db.joinedload(Question.options)).get_or_404(question_id)
    quiz = question.quiz

    if request.method == 'POST':
        question.question_statement = request.form.get('question_statement', '').strip()
        options_texts = request.form.getlist('option_text[]')
        correct_option_index_str = request.form.get('correct_option')

        submitted_data = {'question_statement': question.question_statement, 'options_texts': options_texts, 'correct_option_index_str': correct_option_index_str}

        if not question.question_statement:
            flash('Question statement cannot be empty.', 'warning')
            return render_template('admin/admin_edit_question.html', question=question, quiz=quiz, **submitted_data)

        valid_options = [(i, text.strip()) for i, text in enumerate(options_texts) if text.strip()]
        if len(valid_options) < 2:
            flash('Please provide at least two non-empty options.', 'warning')
            return render_template('admin/admin_edit_question.html', question=question, quiz=quiz, **submitted_data)

        if correct_option_index_str is None:
            flash('Please mark one option as correct.', 'warning')
            return render_template('admin/admin_edit_question.html', question=question, quiz=quiz, **submitted_data)

        try:
            correct_option_index = int(correct_option_index_str)
            if not any(idx == correct_option_index for idx, text in valid_options):
                flash('The selected correct option must not be empty.', 'warning')
                raise ValueError("Correct option is empty")
        except ValueError:
            flash('Invalid correct option selected or the option was empty.', 'danger')
            return render_template('admin/admin_edit_question.html', question=question, quiz=quiz, **submitted_data)

        try:
            Option.query.filter_by(question_id=question.id).delete()
            db.session.flush()

            for i, text in valid_options:
                is_correct = (i == correct_option_index)
                new_opt = Option(
                    question_id=question.id,
                    option_text=text,
                    is_correct=is_correct
                )
                db.session.add(new_opt)

            db.session.commit()
            flash("Question updated successfully!", "success")
            return redirect(url_for('questions_list', quiz_id=quiz.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating question: {e}", "danger")
            question = Question.query.options(db.joinedload(Question.options)).get_or_404(question_id)
            return render_template('admin/admin_edit_question.html', question=question, quiz=quiz, **submitted_data)

    return render_template('admin/admin_edit_question.html', question=question, quiz=quiz)

@app.route('/admin/question/<int:question_id>/delete', methods=['POST'])
@login_required
@admin_required
def question_delete(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    question_statement = question.question_statement
    try:
        db.session.delete(question)
        db.session.commit()
        flash(f"Question '{question_statement[:50]}...' deleted.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting question: {e}", "danger")
    return redirect(url_for('questions_list', quiz_id=quiz_id))

# Admin analytics route
@app.route('/admin/analytics')
@login_required
@admin_required
def admin_analytics():
    user_growth_data = db.session.query(
        func.strftime('%Y-%m', User.created_at),
        func.count(User.id)
    ).filter(User.role == 'user').group_by(
        func.strftime('%Y-%m', User.created_at)
    ).order_by(
        func.strftime('%Y-%m', User.created_at)
    ).all()

    quiz_attempts_data = db.session.query(
        func.strftime('%Y-%m', Score.time_stamp_of_attempt),
        func.count(Score.id)
    ).group_by(
        func.strftime('%Y-%m', Score.time_stamp_of_attempt)
    ).order_by(
        func.strftime('%Y-%m', Score.time_stamp_of_attempt)
    ).all()

    quizzes_by_subject = db.session.query(
        Subject.name, func.count(Quiz.id)
    ).select_from(Subject).join(
        Chapter, Chapter.subject_id == Subject.id
    ).join(
        Quiz, Quiz.chapter_id == Chapter.id
    ).group_by(Subject.name).order_by(Subject.name).all()

    chapters_by_subject = db.session.query(
        Subject.name, func.count(Chapter.id)
    ).select_from(Subject).join(
        Chapter, Chapter.subject_id == Subject.id
    ).group_by(Subject.name).order_by(Subject.name).all()

    total_users = User.query.filter_by(role='user').count()
    total_admins = User.query.filter_by(role='admin').count()
    total_quizzes = Quiz.query.count()
    total_subjects = Subject.query.count()
    total_chapters = Chapter.query.count()
    total_questions = Question.query.count()
    total_attempts = Score.query.count()

    def format_table_data(data):
        labels = [row[0] if row[0] else "Unknown" for row in data]
        values = [row[1] for row in data]
        return labels, values

    userGrowth_labels, userGrowth_values = format_table_data(user_growth_data)
    quizAttempt_labels, quizAttempt_values = format_table_data(quiz_attempts_data)
    quizBySubject_labels, quizBySubject_values = format_table_data(quizzes_by_subject)
    chapterDist_labels, chapterDist_values = format_table_data(chapters_by_subject)

    return render_template(
        'admin/admin_analytics.html',
        total_users=total_users,
        total_admins=total_admins,
        total_quizzes=total_quizzes,
        total_subjects=total_subjects,
        total_chapters=total_chapters,
        total_questions=total_questions,
        total_attempts=total_attempts,
        userGrowth_labels=userGrowth_labels, userGrowth_values=userGrowth_values,
        quizAttempt_labels=quizAttempt_labels, quizAttempt_values=quizAttempt_values,
        quizBySubject_labels=quizBySubject_labels, quizBySubject_values=quizBySubject_values,
        chapterDist_labels=chapterDist_labels, chapterDist_values=chapterDist_values
    )

# Admin user management routes
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15

    query = User.query
    if search_query:
        search_term = f'%{search_query}%'
        query = query.filter(
            or_(
                User.username.ilike(search_term),
                User.full_name.ilike(search_term)
            )
        )

    users_pagination = query.order_by(User.username).paginate(page=page, per_page=per_page, error_out=False)
    users = users_pagination.items

    return render_template(
        'admin/admin_users.html',
        users=users,
        pagination=users_pagination,
        search_query=search_query
    )

@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', 'user')
        qualification = request.form.get('qualification', '').strip()
        dob_str = request.form.get('dob')

        submitted_data = {'username': username, 'full_name': full_name, 'role': role, 'qualification': qualification, 'dob': dob_str}

        if not username or not password or not full_name:
            flash("Username, Password, and Full Name are required.", "warning")
            return render_template('admin/admin_create_user.html', **submitted_data)

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return render_template('admin/admin_create_user.html', **submitted_data)

        if role not in ['user', 'admin']:
            flash("Invalid role selected.", "warning")
            return render_template('admin/admin_create_user.html', **submitted_data)

        if User.query.filter(func.lower(User.username) == func.lower(username)).first():
            flash("Username already exists.", "warning")
            return render_template('admin/admin_create_user.html', **submitted_data)

        dob_obj = None
        if dob_str:
            try:
                dob_obj = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format for DOB. Use YYYY-MM-DD.', 'warning')
                return render_template('admin/admin_create_user.html', **submitted_data)

        try:
            new_user = User(
                username=username,
                full_name=full_name,
                role=role,
                qualification=qualification,
                dob=dob_obj
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f"User '{username}' created successfully.", "success")
            return redirect(url_for('admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating user: {e}", "danger")
            return render_template('admin/admin_create_user.html', **submitted_data)

    return render_template('admin/admin_create_user.html', role='user')

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)

    if request.method == 'POST':
        original_full_name = user_to_edit.full_name
        original_role = user_to_edit.role
        original_qualification = user_to_edit.qualification
        original_dob = user_to_edit.dob

        new_full_name = request.form.get('full_name', '').strip()
        new_role = request.form.get('role', user_to_edit.role)
        new_qualification = request.form.get('qualification', '').strip()
        dob_str = request.form.get('dob')
        new_password = request.form.get('password')

        if not new_full_name:
            flash("Full Name is required.", "warning")
            user_to_edit.dob_str = dob_str
            return render_template('admin/admin_edit_user.html', user=user_to_edit)

        if new_role not in ['user', 'admin']:
            flash("Invalid role selected.", "warning")
            user_to_edit.dob_str = dob_str
            return render_template('admin/admin_edit_user.html', user=user_to_edit)

        if user_to_edit.role == 'admin' and new_role == 'user':
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count <= 1:
                flash("Cannot change the role of the last admin.", "danger")
                user_to_edit.dob_str = dob_str
                return render_template('admin/admin_edit_user.html', user=user_to_edit)

        dob_obj = None
        if dob_str:
            try:
                dob_obj = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format for DOB. Use YYYY-MM-DD.', 'warning')
                user_to_edit.dob_str = dob_str
                return render_template('admin/admin_edit_user.html', user=user_to_edit)

        try:
            user_to_edit.full_name = new_full_name
            user_to_edit.role = new_role
            user_to_edit.qualification = new_qualification
            user_to_edit.dob = dob_obj

            password_updated = False
            if new_password:
                user_to_edit.set_password(new_password)
                password_updated = True

            db.session.commit()

            flash_messages = ["User updated successfully."]
            if password_updated:
                flash_messages.append("User password updated.")
            flash(" ".join(flash_messages), "success")
            return redirect(url_for('admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating user: {e}", "danger")
            user_to_edit.full_name = original_full_name
            user_to_edit.role = original_role
            user_to_edit.qualification = original_qualification
            user_to_edit.dob = original_dob
            user_to_edit.dob_str = dob_str
            return render_template('admin/admin_edit_user.html', user=user_to_edit)

    user_to_edit.dob_str = user_to_edit.dob.strftime('%Y-%m-%d') if user_to_edit.dob else ''
    return render_template('admin/admin_edit_user.html', user=user_to_edit)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('admin_users'))

    if user_to_delete.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash("Cannot delete the last remaining admin user!", "danger")
            return redirect(url_for('admin_users'))

    username = user_to_delete.username
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f"User '{username}' deleted successfully.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user '{username}': {e}", "danger")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/export_csv')
@login_required
@admin_required
def export_users_csv():
    all_users = User.query.order_by(User.username).all()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['UserID', 'Username', 'FullName', 'Role', 'Qualification', 'DOB', 'RegisteredAt'])
    for user in all_users:
        writer.writerow([
            user.id, user.username, user.full_name, user.role,
            user.qualification or '',
            user.dob.strftime('%Y-%m-%d') if user.dob else '',
            user.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    csv_data = output.getvalue()
    output.close()

    return (
        csv_data, 200, {
            "Content-Type": "text/csv",
            "Content-Disposition": f"attachment; filename=users_export_{date.today().isoformat()}.csv"
        }
    )

# --- USER ROUTES ---

@app.route('/dashboard')
@login_required
def dashboard_user():
    if current_user.role == 'admin':
        return redirect(url_for('dashboard_admin'))

    quizzes = Quiz.query.options(
        db.joinedload(Quiz.chapter).joinedload(Chapter.subject)
    ).order_by(Quiz.date_of_quiz.desc()).all()

    past_scores = Score.query.filter_by(user_id=current_user.id)\
                             .options(db.joinedload(Score.quiz))\
                             .order_by(Score.time_stamp_of_attempt.desc())\
                             .limit(5).all()

    # Full set of quiz IDs the user has ever attempted (used for correct
    # "already attempted" display across ALL quizzes, not just last 5)
    attempted_quiz_ids = {
        row[0] for row in
        db.session.query(Score.quiz_id).filter_by(user_id=current_user.id).all()
    }

    return render_template(
        'user/user_dashboard.html',
        quizzes=quizzes,
        past_scores=past_scores,
        attempted_quiz_ids=attempted_quiz_ids
    )

@app.route('/quiz/<int:quiz_id>/attempt', methods=['GET', 'POST'])
@login_required
def attempt_quiz(quiz_id):
    if current_user.role == 'admin':
        flash('Admins cannot attempt quizzes.', 'warning')
        return redirect(url_for('dashboard_admin'))

    quiz = Quiz.query.options(
        db.joinedload(Quiz.questions).joinedload(Question.options)
    ).get_or_404(quiz_id)

    questions = quiz.questions
    total_possible_score = len(questions)

    if request.method == 'POST':
        score = 0
        try:
            for question in questions:
                selected_option_id_str = request.form.get(f'question_{question.id}')
                if selected_option_id_str:
                    selected_option_id = int(selected_option_id_str)
                    chosen_option = next((opt for opt in question.options if opt.id == selected_option_id), None)
                    if chosen_option and chosen_option.is_correct:
                        score += 1

            new_score = Score(
                quiz_id=quiz_id,
                user_id=current_user.id,
                total_scored=score,
                total_possible=total_possible_score
            )
            db.session.add(new_score)
            db.session.commit()

            flash(f'Quiz "{quiz.name}" submitted! You scored {score} out of {total_possible_score}.', 'success')
            return redirect(url_for('quiz_history'))

        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while submitting your answers: {e}", "danger")
            return render_template('user/user_attempt_quiz.html', quiz=quiz, questions=questions)

    return render_template('user/user_attempt_quiz.html', quiz=quiz, questions=questions)

@app.route('/quiz/history')
@login_required
def quiz_history():
    if current_user.role == 'admin':
        flash('Admins do not have quiz attempt histories.', 'info')
        return redirect(url_for('dashboard_admin'))

    user_scores = Score.query.filter_by(user_id=current_user.id)\
                             .options(db.joinedload(Score.quiz).joinedload(Quiz.chapter).joinedload(Chapter.subject))\
                             .order_by(Score.time_stamp_of_attempt.desc())\
                             .all()

    return render_template('user/user_history.html', user_scores=user_scores)


# --- ERROR HANDLERS ---

@app.errorhandler(403)
def forbidden_error(error):
    logger.warning("403 Forbidden: %s", request.url)
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found_error(error):
    logger.info("404 Not Found: %s", request.url)
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error("500 Internal Server Error: %s | URL: %s", error, request.url, exc_info=True)
    db.session.rollback()  # Roll back any failed transaction
    return render_template('errors/500.html'), 500
