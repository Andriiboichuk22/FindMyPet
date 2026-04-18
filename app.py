from functools import wraps
import os
from uuid import uuid4

from flask import Flask, render_template, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

app = Flask(__name__)

# CONFIG
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secret_key_123"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)


def init_app_data():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
        ensure_user_columns()


def ensure_user_columns():
    columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(user)")).fetchall()
    }

    if 'phone' not in columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN phone VARCHAR(20)"))

    if 'photo' not in columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN photo VARCHAR(200)"))

    db.session.commit()


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def save_uploaded_file(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ""

    original_name = secure_filename(file_storage.filename)
    if not original_name:
        return ""

    filename = f"{prefix}_{uuid4().hex}_{original_name}"
    file_storage.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            flash("Спочатку увійдіть у свій акаунт")
            return redirect('/login')
        return view_func(*args, **kwargs)

    return wrapped_view


@app.context_processor
def inject_user():
    current_user = get_current_user()
    return {
        'user': current_user.username if current_user else None,
        'current_user': current_user
    }

# =========================
# USER MODEL
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    photo = db.Column(db.String(200))

    # 🔥 зворотний зв'язок (опціонально)
    pets = db.relationship('Pet', backref='user', lazy=True)


# =========================
# PET MODEL
# =========================
class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(50), nullable=False)
    animal_type = db.Column(db.String(50))
    breed = db.Column(db.String(100))
    age = db.Column(db.String(50))

    location = db.Column(db.String(100))
    date = db.Column(db.String(50))
    phone = db.Column(db.String(20))

    photo = db.Column(db.String(200))

    # 🔥 зв’язок з користувачем
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


# =========================
# HOME
# =========================
@app.route('/')
def home():
    pets = Pet.query.all()
    return render_template('index.html', pets=pets)


# =========================
# ADD PET
# =========================
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    current_user = get_current_user()

    if request.method == 'POST':
        file = request.files.get('photo')
        filename = save_uploaded_file(file, 'pet')
        phone = request.form['phone'].strip() or (current_user.phone or "")

        pet = Pet(
            title=request.form['title'],
            description=request.form['description'],
            status=request.form['status'],

            animal_type=request.form['animal_type'],
            breed=request.form['breed'],
            age=request.form['age'],

            location=request.form['location'],
            date=request.form['date'],
            phone=phone,

            photo=filename,
            user_id=current_user.id
        )

        db.session.add(pet)
        db.session.commit()

        return redirect('/')

    return render_template('add.html', profile_user=current_user)


# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, password=password).first()

        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect('/')
        else:
            flash("Невірний логін або пароль")

    return render_template('login.html')


# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Користувач з таким логіном уже існує")
            return render_template('register.html')

        user = User(
            username=username,
            password=password
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Користувач з таким логіном уже існує")
            return render_template('register.html')

        return redirect('/login')

    return render_template('register.html')


@app.route('/cabinet', methods=['GET', 'POST'])
@login_required
def cabinet():
    current_user = get_current_user()

    if request.method == 'POST':
        current_user.username = request.form['username'].strip()
        current_user.phone = request.form['phone'].strip()

        file = request.files.get('photo')
        if file and file.filename:
            current_user.photo = save_uploaded_file(file, 'profile')

        try:
            db.session.commit()
            session['username'] = current_user.username
            flash("Профіль оновлено")
        except IntegrityError:
            db.session.rollback()
            flash("Такий логін уже зайнятий")

        return redirect('/cabinet')

    user_pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.id.desc()).all()
    return render_template('cabinet.html', profile_user=current_user, user_pets=user_pets)


@app.route('/pets/<int:pet_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pet(pet_id):
    current_user = get_current_user()
    pet = Pet.query.get_or_404(pet_id)

    if pet.user_id != current_user.id:
        flash("Ви не можете редагувати це оголошення")
        return redirect('/cabinet')

    if request.method == 'POST':
        pet.title = request.form['title']
        pet.description = request.form['description']
        pet.status = request.form['status']
        pet.animal_type = request.form['animal_type']
        pet.breed = request.form['breed']
        pet.age = request.form['age']
        pet.location = request.form['location']
        pet.date = request.form['date']
        pet.phone = request.form['phone'].strip() or (current_user.phone or "")

        file = request.files.get('photo')
        if file and file.filename:
            pet.photo = save_uploaded_file(file, 'pet')

        db.session.commit()
        flash("Оголошення оновлено")
        return redirect('/cabinet')

    return render_template('edit_pet.html', pet=pet, profile_user=current_user)


# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# =========================
# RUN APP
# =========================
init_app_data()

if __name__ == '__main__':
    app.run(debug=True)
