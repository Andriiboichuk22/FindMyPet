from functools import wraps
from datetime import datetime
from email.message import EmailMessage
import re
import os
import secrets
import smtplib
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
import requests
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
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
RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY') or getattr(config, 'RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY') or getattr(config, 'RECAPTCHA_SECRET_KEY', '')
RECAPTCHA_MIN_SCORE = float(os.getenv('RECAPTCHA_MIN_SCORE') or getattr(config, 'RECAPTCHA_MIN_SCORE', 0.5))
MAIL_SERVER = os.getenv('MAIL_SERVER') or getattr(config, 'MAIL_SERVER', '')
MAIL_PORT = int(os.getenv('MAIL_PORT') or getattr(config, 'MAIL_PORT', 587))
MAIL_USE_TLS = (os.getenv('MAIL_USE_TLS') or str(getattr(config, 'MAIL_USE_TLS', 'true'))).lower() in {'1', 'true', 'yes', 'on'}
MAIL_USERNAME = os.getenv('MAIL_USERNAME') or getattr(config, 'MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD') or getattr(config, 'MAIL_PASSWORD', '')
MAIL_FROM = os.getenv('MAIL_FROM') or getattr(config, 'MAIL_FROM', MAIL_USERNAME)
PASSWORD_RESET_SALT = os.getenv('PASSWORD_RESET_SALT') or getattr(config, 'PASSWORD_RESET_SALT', 'password-reset-salt')
PASSWORD_RESET_EXPIRES_MINUTES = int(
    os.getenv('PASSWORD_RESET_EXPIRES_MINUTES') or getattr(config, 'PASSWORD_RESET_EXPIRES_MINUTES', 30)
)
EMAIL_VERIFICATION_SALT = os.getenv('EMAIL_VERIFICATION_SALT') or getattr(config, 'EMAIL_VERIFICATION_SALT', 'email-verification-salt')
EMAIL_VERIFICATION_EXPIRES_HOURS = int(
    os.getenv('EMAIL_VERIFICATION_EXPIRES_HOURS') or getattr(config, 'EMAIL_VERIFICATION_EXPIRES_HOURS', 24)
)

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


def get_token_serializer():
    return URLSafeTimedSerializer(app.secret_key)


def hash_password(password):
    return generate_password_hash(password)


def validate_password_strength(password):
    if len(password) < 8:
        return 'Пароль має містити щонайменше 8 символів'
    if not re.search(r'[A-Z]', password):
        return 'Пароль має містити хоча б одну велику літеру'
    if not re.search(r'[a-z]', password):
        return 'Пароль має містити хоча б одну малу літеру'
    if not re.search(r'\d', password):
        return 'Пароль має містити хоча б одну цифру'
    if not re.search(r'[^A-Za-z0-9]', password):
        return 'Пароль має містити хоча б один спеціальний символ'
    return None


def is_recaptcha_configured():
    return bool(RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY)


def validate_recaptcha_token(recaptcha_token, expected_action):
    if not is_recaptcha_configured():
        return None

    if not recaptcha_token:
        return 'Підтвердіть, що ви не робот, через Google reCAPTCHA'

    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': RECAPTCHA_SECRET_KEY,
                'response': recaptcha_token,
                'remoteip': request.remote_addr,
            },
            timeout=10,
        )
        payload = response.json()
    except requests.RequestException:
        return 'Не вдалося перевірити Google reCAPTCHA. Спробуйте ще раз трохи пізніше'

    if not payload.get('success'):
        return 'Google reCAPTCHA не пройдена. Спробуйте ще раз'

    action = payload.get('action')
    score = float(payload.get('score') or 0)

    if action != expected_action:
        return 'Google reCAPTCHA повернула некоректну дію. Спробуйте ще раз'

    if score < RECAPTCHA_MIN_SCORE:
        return 'Перевірка Google reCAPTCHA не пройдена. Спробуйте ще раз'

    return None


def verify_password(user, password):
    if not user or not user.password:
        return False

    stored_password = user.password

    # Keep old plain-text records working, then upgrade them after a successful login.
    if stored_password == password:
        return True

    if stored_password.startswith('scrypt:') or stored_password.startswith('pbkdf2:'):
        return check_password_hash(stored_password, password)

    return False


def normalize_email(value):
    return value.strip().lower()


def is_mail_configured():
    return all([MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM])


def send_email_message(subject, recipient, body):
    if not is_mail_configured():
        return False

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = MAIL_FROM
    message['To'] = recipient
    message.set_content(body)

    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
        if MAIL_USE_TLS:
            smtp.starttls()
        smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
        smtp.send_message(message)

    return True


def generate_password_reset_token(user):
    serializer = get_token_serializer()
    return serializer.dumps(user.email, salt=PASSWORD_RESET_SALT)


def verify_password_reset_token(token):
    serializer = get_token_serializer()
    email = serializer.loads(
        token,
        salt=PASSWORD_RESET_SALT,
        max_age=PASSWORD_RESET_EXPIRES_MINUTES * 60,
    )
    return User.query.filter_by(email=email).first()


def generate_email_verification_token(user):
    serializer = get_token_serializer()
    return serializer.dumps(user.email, salt=EMAIL_VERIFICATION_SALT)


def verify_email_verification_token(token):
    serializer = get_token_serializer()
    email = serializer.loads(
        token,
        salt=EMAIL_VERIFICATION_SALT,
        max_age=EMAIL_VERIFICATION_EXPIRES_HOURS * 3600,
    )
    return User.query.filter_by(email=email).first()


def send_email_verification(user):
    verification_token = generate_email_verification_token(user)
    verification_link = url_for('verify_email', token=verification_token, _external=True)
    email_body = (
        'Підтвердіть свою пошту для FindMyPet.\n\n'
        f'Перейдіть за посиланням:\n{verification_link}\n\n'
        f'Посилання дійсне {EMAIL_VERIFICATION_EXPIRES_HOURS} годин.\n'
        'Якщо ви не створювали акаунт, просто проігноруйте цей лист.'
    )
    send_email_message('FindMyPet - підтвердження пошти', user.email, email_body)


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            flash('Спочатку увійдіть у свій акаунт')
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapped_view


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            flash('Спочатку увійдіть у свій акаунт')
            return redirect(url_for('login'))
        if not current_user.is_admin:
            flash('Доступ до адмінки мають лише адміністратори')
            return redirect(url_for('home'))
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
        'recaptcha_enabled': is_recaptcha_configured(),
        'recaptcha_site_key': RECAPTCHA_SITE_KEY,
        'mail_configured': is_mail_configured(),
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
    is_email_verified = db.Column(db.Boolean, nullable=False, default=True)
    google_id = db.Column(db.String(255), unique=True)
    auth_provider = db.Column(db.String(20), nullable=False, default='local')
    is_username_auto = db.Column(db.Boolean, nullable=False, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    pets = db.relationship('Pet', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='user', lazy=True)


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
    comments = db.relationship('Comment', backref='pet', lazy=True, cascade='all, delete-orphan')


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


def ensure_user_columns():
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(user)')).fetchall()
    }

    statements = {
        'phone': 'ALTER TABLE user ADD COLUMN phone VARCHAR(20)',
        'photo': 'ALTER TABLE user ADD COLUMN photo VARCHAR(200)',
        'email': 'ALTER TABLE user ADD COLUMN email VARCHAR(255)',
        'is_email_verified': 'ALTER TABLE user ADD COLUMN is_email_verified BOOLEAN DEFAULT 1 NOT NULL',
        'google_id': 'ALTER TABLE user ADD COLUMN google_id VARCHAR(255)',
        'auth_provider': "ALTER TABLE user ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local' NOT NULL",
        'is_username_auto': 'ALTER TABLE user ADD COLUMN is_username_auto BOOLEAN DEFAULT 0 NOT NULL',
        'is_admin': 'ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0 NOT NULL',
    }

    for column_name, statement in statements.items():
        if column_name not in columns:
            db.session.execute(text(statement))

    db.session.execute(text("UPDATE user SET auth_provider = 'local' WHERE auth_provider IS NULL OR auth_provider = ''"))
    db.session.execute(text("UPDATE user SET is_username_auto = 0 WHERE is_username_auto IS NULL"))
    db.session.execute(text("UPDATE user SET is_email_verified = 1 WHERE is_email_verified IS NULL"))
    db.session.execute(text("UPDATE user SET is_admin = 0 WHERE is_admin IS NULL"))
    db.session.commit()


def ensure_admin_user():
    admin_user = User.query.filter_by(username='admin').first()

    if not admin_user:
        admin_user = User.query.filter_by(email='findmypetadmin@gmail.com').first()

    if admin_user:
        admin_user.username = 'admin'
        admin_user.is_admin = True
        admin_user.email = admin_user.email or 'findmypetadmin@gmail.com'
        admin_user.auth_provider = admin_user.auth_provider or 'local'
        admin_user.is_username_auto = False
        admin_user.is_email_verified = True
        admin_user.password = hash_password('admin')
    else:
        admin_user = User(
            username='admin',
            password=hash_password('admin'),
            email='findmypetadmin@gmail.com',
            auth_provider='local',
            is_email_verified=True,
            is_username_auto=False,
            is_admin=True,
        )
        db.session.add(admin_user)

    db.session.commit()


def init_app_data():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
        ensure_user_columns()
        ensure_admin_user()


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


@app.route('/pets/<int:pet_id>/comments', methods=['POST'])
@login_required
def add_comment(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    current_user = get_current_user()
    content = request.form['content'].strip()

    if not content:
        flash('Р’С–РґРіСѓРє РЅРµ РјРѕР¶Рµ Р±СѓС‚Рё РїРѕСЂРѕР¶РЅС–Рј')
        return redirect(url_for('home', **request.args))

    comment = Comment(
        content=content,
        pet_id=pet.id,
        user_id=current_user.id,
    )
    db.session.add(comment)
    db.session.commit()
    flash('Р’С–РґРіСѓРє РґРѕРґР°РЅРѕ')
    return redirect(url_for('home', **request.args))


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
        flash('РћРіРѕР»РѕС€РµРЅРЅСЏ РѕРїСѓР±Р»С–РєРѕРІР°РЅРѕ')
        return redirect(url_for('home'))

    return render_template('add.html', profile_user=current_user)


# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_value = request.form['username'].strip()
        password = request.form['password']
        recaptcha_error = validate_recaptcha_token(
            request.form.get('g-recaptcha-response', ''),
            expected_action='login',
        )
        if recaptcha_error:
            flash(recaptcha_error)
            return render_template('login.html')
        search_value = normalize_email(login_value)
        user = User.query.filter(
            or_(
                User.username == login_value,
                User.email == search_value,
            )
        ).first()

        if verify_password(user, password):
            if user.auth_provider == 'local' and user.email and not user.is_email_verified:
                flash('Спочатку підтвердіть пошту. Ми надіслали вам лист із посиланням.')
                return redirect(url_for('resend_verification'))
            if user.password == password:
                user.password = hash_password(password)
                db.session.commit()
            set_logged_in_user(user)
            if user.is_username_auto:
                return redirect(url_for('complete_profile'))
            return redirect(url_for('home'))

        flash('Невірний логін або пароль')

    return render_template('login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = normalize_email(request.form['email'])

        if not email:
            flash('Вкажіть email для відновлення пароля')
            return render_template('forgot_password.html')

        if not is_mail_configured():
            flash('Відновлення пароля через пошту ще не налаштоване. Додайте SMTP-параметри в config.py або змінні середовища.')
            return render_template('forgot_password.html')

        user = User.query.filter_by(email=email).first()
        if user and user.auth_provider == 'local' and user.is_email_verified:
            token = generate_password_reset_token(user)
            reset_link = url_for('reset_password', token=token, _external=True)
            email_body = (
                'Ви запросили скидання пароля для FindMyPet.\n\n'
                f'Перейдіть за посиланням, щоб встановити новий пароль:\n{reset_link}\n\n'
                f'Посилання дійсне {PASSWORD_RESET_EXPIRES_MINUTES} хвилин.\n'
                'Якщо це були не ви, просто проігноруйте цей лист.'
            )

            try:
                send_email_message('FindMyPet - відновлення пароля', user.email, email_body)
            except Exception:
                flash('Не вдалося надіслати листа. Перевірте SMTP-налаштування пошти.')
                return render_template('forgot_password.html')

        flash('Якщо акаунт з таким email існує, ми надіслали інструкцію для відновлення пароля.')
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/verify-email/<token>')
def verify_email(token):
    try:
        user = verify_email_verification_token(token)
    except SignatureExpired:
        flash('Посилання для підтвердження пошти вже неактивне. Запросіть нове.')
        return redirect(url_for('resend_verification'))
    except BadSignature:
        flash('Некоректне посилання для підтвердження пошти.')
        return redirect(url_for('login'))

    if not user or user.auth_provider != 'local':
        flash('Підтвердження пошти для цього акаунта недоступне.')
        return redirect(url_for('login'))

    user.is_email_verified = True
    db.session.commit()
    flash('Пошту підтверджено. Тепер ви можете увійти.')
    return redirect(url_for('login'))


@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        email = normalize_email(request.form['email'])

        if not email:
            flash('Вкажіть email')
            return render_template('resend_verification.html')

        if not is_mail_configured():
            flash('Надсилання листів ще не налаштоване. Додайте SMTP-параметри в config.py.')
            return render_template('resend_verification.html')

        user = User.query.filter_by(email=email).first()
        if user and user.auth_provider == 'local' and not user.is_email_verified:
            try:
                send_email_verification(user)
            except Exception:
                flash('Не вдалося надіслати листа. Перевірте SMTP-налаштування пошти.')
                return render_template('resend_verification.html')

        flash('Якщо акаунт існує і пошта ще не підтверджена, ми надіслали новий лист.')
        return redirect(url_for('login'))

    return render_template('resend_verification.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        user = verify_password_reset_token(token)
    except SignatureExpired:
        flash('Посилання для відновлення пароля вже неактивне. Запросіть нове.')
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash('Некоректне посилання для відновлення пароля.')
        return redirect(url_for('forgot_password'))

    if not user or user.auth_provider != 'local':
        flash('Для цього акаунта відновлення пароля недоступне.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error)
            return render_template('reset_password.html', token=token)

        if password != confirm_password:
            flash('Паролі не збігаються')
            return render_template('reset_password.html', token=token)

        user.password = hash_password(password)
        db.session.commit()
        flash('Пароль оновлено. Тепер увійдіть з новим паролем.')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


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
        email = normalize_email(request.form['email'])
        password = request.form['password']
        recaptcha_error = validate_recaptcha_token(
            request.form.get('g-recaptcha-response', ''),
            expected_action='register',
        )
        if recaptcha_error:
            flash(recaptcha_error)
            return render_template('register.html')

        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error)
            return render_template('register.html')

        if not email:
            flash('Вкажіть email')
            return render_template('register.html')

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Користувач з таким логіном уже існує')
            return render_template('register.html')

        existing_email_user = User.query.filter_by(email=email).first()
        if existing_email_user:
            flash('Користувач з таким email уже існує')
            return render_template('register.html')

        user = User(
            username=username,
            password=hash_password(password),
            email=email,
            auth_provider='local',
            is_email_verified=False,
            is_username_auto=False,
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Логін або email уже зайнятий')
            return render_template('register.html')

        if is_mail_configured():
            try:
                send_email_verification(user)
            except Exception:
                flash('Акаунт створено, але лист підтвердження не вдалося надіслати. Спробуйте ще раз пізніше.')
                return redirect(url_for('resend_verification'))

            flash('Акаунт створено. Перевірте пошту й підтвердьте email перед входом.')
        else:
            flash('Акаунт створено, але надсилання листів ще не налаштоване. Зверніться до адміністратора.')
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
        new_email = normalize_email(request.form['email'])
        email_changed = new_email != (current_user.email or '')
        current_user.phone = request.form['phone'].strip()

        if current_user.auth_provider == 'local' and email_changed and not is_mail_configured():
            flash('Спочатку налаштуйте пошту для сайту, щоб змінювати email із підтвердженням.')
            return redirect(url_for('cabinet'))

        if not new_email:
            flash('Вкажіть email')
            return redirect(url_for('cabinet'))

        existing_user = User.query.filter_by(username=new_username).first()
        if existing_user and existing_user.id != current_user.id:
            flash('Такий логін уже зайнятий')
            return redirect(url_for('cabinet'))

        existing_email_user = User.query.filter_by(email=new_email).first()
        if existing_email_user and existing_email_user.id != current_user.id:
            flash('Користувач з таким email уже існує')
            return redirect(url_for('cabinet'))

        current_user.username = new_username
        current_user.email = new_email
        if current_user.auth_provider == 'local' and email_changed:
            current_user.is_email_verified = False
        current_user.is_username_auto = False

        file = request.files.get('photo')
        if file and file.filename:
            current_user.photo = save_uploaded_file(file, 'profile')

        try:
            db.session.commit()
            if current_user.auth_provider == 'local' and email_changed and is_mail_configured():
                try:
                    send_email_verification(current_user)
                except Exception:
                    flash('Email оновлено, але лист підтвердження не вдалося надіслати.')
                    return redirect(url_for('cabinet'))
            set_logged_in_user(current_user)
            if current_user.auth_provider == 'local' and email_changed:
                flash('Профіль оновлено. Підтвердьте нову пошту через лист.')
            else:
                flash('Профіль оновлено')
        except IntegrityError:
            db.session.rollback()
            flash('Логін або email уже зайнятий')

        return redirect(url_for('cabinet'))

    user_pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.id.desc()).all()
    return render_template('cabinet.html', profile_user=current_user, user_pets=user_pets)


@app.route('/admin')
@admin_required
def admin_panel():
    pets = Pet.query.order_by(Pet.id.desc()).all()
    return render_template('admin.html', pets=pets)

@app.route('/pets/<int:pet_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pet(pet_id):
    current_user = get_current_user()
    pet = Pet.query.get_or_404(pet_id)

    if pet.user_id != current_user.id:
        flash('Р’Рё РЅРµ РјРѕР¶РµС‚Рµ СЂРµРґР°РіСѓРІР°С‚Рё С†Рµ РѕРіРѕР»РѕС€РµРЅРЅСЏ')
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
        flash('РћРіРѕР»РѕС€РµРЅРЅСЏ РѕРЅРѕРІР»РµРЅРѕ')
        return redirect(url_for('cabinet'))

    return render_template('edit_pet.html', pet=pet, profile_user=current_user)


@app.route('/pets/<int:pet_id>/delete', methods=['POST'])
@login_required
def delete_pet(pet_id):
    current_user = get_current_user()
    pet = Pet.query.get_or_404(pet_id)

    if pet.user_id != current_user.id and not current_user.is_admin:
        flash('Ви не можете видалити це оголошення')
        return redirect(url_for('cabinet'))

    db.session.delete(pet)
    db.session.commit()
    flash('Оголошення видалено')

    if current_user.is_admin and pet.user_id != current_user.id:
        return redirect(url_for('admin_panel'))
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










