from datetime import datetime, date
from models.database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    qualification = db.Column(db.String(100))
    dob = db.Column(db.Date)
    role = db.Column(db.String(10), default='user', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship: a user may have many scores
    scores = db.relationship('Score', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.Text)
    
    # One subject has many chapters
    chapters = db.relationship('Chapter', backref='subject', lazy=True, cascade='all, delete-orphan')


class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # One chapter has many quizzes
    quizzes = db.relationship('Quiz', backref='chapter', lazy=True, cascade='all, delete-orphan')


class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    date_of_quiz = db.Column(db.Date, nullable=False, default=date.today)
    time_duration = db.Column(db.String(5), nullable=False)  # e.g., "30:00"
    remarks = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships: a quiz has many questions and scores
    questions = db.relationship('Question', backref='quiz', lazy=True, cascade='all, delete-orphan')
    scores = db.relationship('Score', backref='quiz', lazy=True, cascade='all, delete-orphan')


class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False, index=True)
    question_statement = db.Column(db.Text, nullable=False)
    
    # One question has many options
    options = db.relationship('Option', backref='question', lazy=True, cascade='all, delete-orphan')


class Option(db.Model):
    __tablename__ = 'options'
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False, index=True)
    option_text = db.Column(db.String(300), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)


class Score(db.Model):
    __tablename__ = 'scores'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    time_stamp_of_attempt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    total_scored = db.Column(db.Integer, nullable=False)
    total_possible = db.Column(db.Integer, nullable=False)
