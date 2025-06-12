from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
import spacy
from collections import Counter
import random
from PyPDF2 import PdfReader

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
Bootstrap(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

nlp = spacy.load("en_core_web_sm")

# --- User Model ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Helper: PDF Processing ---
def process_pdf(file):
    text = ""
    pdf_reader = PdfReader(file)
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

# --- Helper: MCQ Generation ---
def generate_mcqs(text, num_questions=5):
    if text is None:
        return []

    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    num_questions = min(num_questions, len(sentences))
    selected_sentences = random.sample(sentences, num_questions)
    mcqs = []

    for sentence in selected_sentences:
        sent_doc = nlp(sentence)
        nouns = [token.text for token in sent_doc if token.pos_ == "NOUN"]

        if len(nouns) < 2:
            continue

        noun_counts = Counter(nouns)
        if noun_counts:
            subject = noun_counts.most_common(1)[0][0]
            question_stem = sentence.replace(subject, "______")
            answer_choices = [subject]
            distractors = list(set(nouns) - {subject})

            while len(distractors) < 3:
                distractors.append("[Distractor]")

            random.shuffle(distractors)
            for distractor in distractors[:3]:
                answer_choices.append(distractor)

            random.shuffle(answer_choices)
            correct_answer = chr(64 + answer_choices.index(subject) + 1)
            mcqs.append((question_stem, answer_choices, correct_answer))

    return mcqs

# --- Routes ---

@app.route('/')
def home():
    return redirect(url_for('welcome'))

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/task-manager')
@login_required
def task_manager():
    return render_template('task_manager.html', user=current_user)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('welcome'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        text = ""
        if 'files[]' in request.files:
            files = request.files.getlist('files[]')
            for file in files:
                if file.filename.endswith('.pdf'):
                    text += process_pdf(file)
                elif file.filename.endswith('.txt'):
                    text += file.read().decode('utf-8')
        else:
            text = request.form['text']

        num_questions = int(request.form['num_questions'])
        mcqs = generate_mcqs(text, num_questions)
        mcqs_with_index = [(i + 1, mcq) for i, mcq in enumerate(mcqs)]

        # Store MCQs in session or db temporarily (optional)
        return render_template('mcqs.html', mcqs=mcqs_with_index)

    return render_template('index.html')

# --- Run ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
