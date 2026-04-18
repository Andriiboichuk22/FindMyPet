from functools import wraps
import os
import secrets
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

import config

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None


app = Flask(__name__)

# CONFIG
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('FLASK_SECRET_KEY') or config.FLASK_SECRET_KEY or 'secret_key_123'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID') or config.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET') or config.GOOGLE_CLIENT_SECRET

db = SQLAlchemy(app)
oauth = None
google_oauth = None


def slugify_username(value):
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {' ', '_', '-'}:
            allowed.append('_')

    username = ''.join(allowed).strip('_')
    while '__' in username:
        username = username.replace('__', '_')
    return username[:30]


def generate_unique_username(base_value):
    base = slugify_username(base_value) or 'pet_friend'
    candidate = base
    counter = 1

    while User.query.filter_by(username=candidate).first():
        candidate = f'{base}_{counter}'
        counter += 1

    return candidate


def save_uploaded_file(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ''

    original_name = secure_filename(file_storage.filename)
    if not original_name:
        return ''

    filename = f'{prefix}_{uuid4().hex}_{original_name}'
    file_storage.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def set_logged_in_user(user):
    session['user_id'] = user.id
    session['username'] = user.username


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            flash('Спочатку увійдіть у свій акаунт')
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapped_view


def setup_google_oauth():
    global oauth, google_oauth

    if OAuth is None or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return

    oauth = OAuth(app)
    google_oauth = oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid profile email'},
    )


@app.context_processor
def inject_user():
    current_user = get_current_user()
    return {
        'user': current_user.username if current_user else None,
        'current_user': current_user,
        'google_auth_enabled': google_oauth is not None,
    }


# =========================
# USER MODEL
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False, default='')
    phone = db.Column(db.String(20))
    photo = db.Column(db.String(200))
    email = db.Column(db.String(255), unique=True)
    google_id = db.Column(db.String(255), unique=True)
    auth_provider = db.Column(db.String(20), nullable=False, default='local')
    is_username_auto = db.Column(db.Boolean, nullable=False, default=False)

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


def ensure_user_columns():
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(user)')).fetchall()
    }

    statements = {
        'phone': 'ALTER TABLE user ADD COLUMN phone VARCHAR(20)',
        'photo': 'ALTER TABLE user ADD COLUMN photo VARCHAR(200)',
        'email': 'ALTER TABLE user ADD COLUMN email VARCHAR(255)',
        'google_id': 'ALTER TABLE user ADD COLUMN google_id VARCHAR(255)',
        'auth_provider': "ALTER TABLE user ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local' NOT NULL",
        'is_username_auto': 'ALTER TABLE user ADD COLUMN is_username_auto BOOLEAN DEFAULT 0 NOT NULL',
    }

    for column_name, statement in statements.items():
        if column_name not in columns:
            db.session.execute(text(statement))

    db.session.execute(text("UPDATE user SET auth_provider = 'local' WHERE auth_provider IS NULL OR auth_provider = ''"))
    db.session.execute(text("UPDATE user SET is_username_auto = 0 WHERE is_username_auto IS NULL"))
    db.session.commit()


def init_app_data():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
        ensure_user_columns()


# =========================
# HOME
# =========================
@app.route('/')
def home():
    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    animal_type_filter = request.args.get('animal_type', '').strip()
    location_filter = request.args.get('location', '').strip()

    pets_query = Pet.query

    if search_query:
        search_pattern = f'%{search_query}%'
        pets_query = pets_query.filter(
            or_(
                Pet.title.ilike(search_pattern),
                Pet.description.ilike(search_pattern),
                Pet.breed.ilike(search_pattern),
                Pet.location.ilike(search_pattern),
            )
        )

    if status_filter:
        pets_query = pets_query.filter(Pet.status == status_filter)

    if animal_type_filter:
        pets_query = pets_query.filter(Pet.animal_type == animal_type_filter)

    if location_filter:
        pets_query = pets_query.filter(Pet.location.ilike(f'%{location_filter}%'))

    pets = pets_query.order_by(Pet.id.desc()).all()
    filters = {
        'q': search_query,
        'status': status_filter,
        'animal_type': animal_type_filter,
        'location': location_filter,
    }
    return render_template('index.html', pets=pets, filters=filters)


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
        phone = request.form['phone'].strip() or (current_user.phone or '')

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
            user_id=current_user.id,
        )

        db.session.add(pet)
        db.session.commit()
        flash('Оголошення опубліковано')
        return redirect(url_for('home'))

    return render_template('add.html', profile_user=current_user)


# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = User.query.filter_by(username=username, password=password).first()

        if user:
            set_logged_in_user(user)
            if user.is_username_auto:
                return redirect(url_for('complete_profile'))
            return redirect(url_for('home'))

        flash('Невірний логін або пароль')

    return render_template('login.html')


@app.route('/login/google')
def login_google():
    if google_oauth is None:
        flash('Google-вхід ще не налаштований. Додайте GOOGLE_CLIENT_ID і GOOGLE_CLIENT_SECRET.')
        return redirect(url_for('login'))

    redirect_uri = url_for('google_callback', _external=True)
    nonce = secrets.token_urlsafe(16)
    session['google_nonce'] = nonce
    return google_oauth.authorize_redirect(redirect_uri, nonce=nonce)


@app.route('/auth/google/callback')
def google_callback():
    if google_oauth is None:
        flash('Google-вхід недоступний')
        return redirect(url_for('login'))

    token = google_oauth.authorize_access_token()
    userinfo = token.get('userinfo')
    if not userinfo:
        userinfo = google_oauth.userinfo()

    google_id = userinfo.get('sub')
    email = userinfo.get('email')
    picture = None
    suggested_name = userinfo.get('name') or (email.split('@')[0] if email else 'pet friend')

    user = None
    if google_id:
        user = User.query.filter_by(google_id=google_id).first()
    if not user and email:
        user = User.query.filter_by(email=email).first()

    if user:
        user.google_id = user.google_id or google_id
        user.email = user.email or email
        if picture and not user.photo:
            user.photo = picture
        if user.auth_provider == 'local':
            user.auth_provider = 'google'
    else:
        user = User(
            username=generate_unique_username(suggested_name),
            password='',
            phone='',
            photo=picture,
            email=email,
            google_id=google_id,
            auth_provider='google',
            is_username_auto=True,
        )
        db.session.add(user)

    db.session.commit()
    set_logged_in_user(user)

    if user.is_username_auto:
        flash('Оберіть публічний логін. Email залишиться прихованим.')
        return redirect(url_for('complete_profile'))

    flash('Вхід через Google виконано успішно')
    return redirect(url_for('home'))


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
            flash('Користувач з таким логіном уже існує')
            return render_template('register.html')

        user = User(
            username=username,
            password=password,
            auth_provider='local',
            is_username_auto=False,
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Користувач з таким логіном уже існує')
            return render_template('register.html')

        flash('Акаунт створено. Тепер увійдіть у систему')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    current_user = get_current_user()

    if not current_user.is_username_auto:
        return redirect(url_for('cabinet'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        phone = request.form['phone'].strip()

        if not username:
            flash('Оберіть публічний логін')
            return render_template('complete_profile.html', profile_user=current_user)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != current_user.id:
            flash('Такий логін уже зайнятий')
            return render_template('complete_profile.html', profile_user=current_user)

        current_user.username = username
        current_user.phone = phone
        current_user.is_username_auto = False
        db.session.commit()

        set_logged_in_user(current_user)
        flash('Профіль збережено')
        return redirect(url_for('cabinet'))

    return render_template('complete_profile.html', profile_user=current_user)


# =========================
# CABINET
# =========================
@app.route('/cabinet', methods=['GET', 'POST'])
@login_required
def cabinet():
    current_user = get_current_user()

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        current_user.phone = request.form['phone'].strip()

        existing_user = User.query.filter_by(username=new_username).first()
        if existing_user and existing_user.id != current_user.id:
            flash('Такий логін уже зайнятий')
            return redirect(url_for('cabinet'))

        current_user.username = new_username
        current_user.is_username_auto = False

        file = request.files.get('photo')
        if file and file.filename:
            current_user.photo = save_uploaded_file(file, 'profile')

        try:
            db.session.commit()
            set_logged_in_user(current_user)
            flash('Профіль оновлено')
        except IntegrityError:
            db.session.rollback()
            flash('Такий логін уже зайнятий')

        return redirect(url_for('cabinet'))

    user_pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.id.desc()).all()
    return render_template('cabinet.html', profile_user=current_user, user_pets=user_pets)


@app.route('/pets/<int:pet_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pet(pet_id):
    current_user = get_current_user()
    pet = Pet.query.get_or_404(pet_id)

    if pet.user_id != current_user.id:
        flash('Ви не можете редагувати це оголошення')
        return redirect(url_for('cabinet'))

    if request.method == 'POST':
        pet.title = request.form['title']
        pet.description = request.form['description']
        pet.status = request.form['status']
        pet.animal_type = request.form['animal_type']
        pet.breed = request.form['breed']
        pet.age = request.form['age']
        pet.location = request.form['location']
        pet.date = request.form['date']
        pet.phone = request.form['phone'].strip() or (current_user.phone or '')

        file = request.files.get('photo')
        if file and file.filename:
            pet.photo = save_uploaded_file(file, 'pet')

        db.session.commit()
        flash('Оголошення оновлено')
        return redirect(url_for('cabinet'))

    return render_template('edit_pet.html', pet=pet, profile_user=current_user)


@app.route('/pets/<int:pet_id>/delete', methods=['POST'])
@login_required
def delete_pet(pet_id):
    current_user = get_current_user()
    pet = Pet.query.get_or_404(pet_id)

    if pet.user_id != current_user.id:
        flash('Ви не можете видалити це оголошення')
        return redirect(url_for('cabinet'))

    db.session.delete(pet)
    db.session.commit()
    flash('Оголошення видалено')
    return redirect(url_for('cabinet'))


# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


setup_google_oauth()
init_app_data()

if __name__ == '__main__':
    app.run(debug=True)
