from email.message import EmailMessage
from functools import wraps
import os
import re
import smtplib
from uuid import uuid4

from flask import current_app, flash, redirect, request, session, url_for
import requests
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from extensions import db
from models import User


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
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
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
    return URLSafeTimedSerializer(current_app.secret_key)


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
    return bool(current_app.config.get('RECAPTCHA_SITE_KEY') and current_app.config.get('RECAPTCHA_SECRET_KEY'))


def validate_recaptcha_token(recaptcha_token, expected_action):
    if not is_recaptcha_configured():
        return None

    if not recaptcha_token:
        return 'Підтвердіть, що ви не робот, через Google reCAPTCHA'

    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': current_app.config['RECAPTCHA_SECRET_KEY'],
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

    if score < current_app.config['RECAPTCHA_MIN_SCORE']:
        return 'Перевірка Google reCAPTCHA не пройдена. Спробуйте ще раз'

    return None


def verify_password(user, password):
    if not user or not user.password:
        return False

    stored_password = user.password
    if stored_password == password:
        return True

    if stored_password.startswith('scrypt:') or stored_password.startswith('pbkdf2:'):
        return check_password_hash(stored_password, password)

    return False


def normalize_email(value):
    return value.strip().lower()


def is_mail_configured():
    return all(
        [
            current_app.config.get('MAIL_SERVER'),
            current_app.config.get('MAIL_PORT'),
            current_app.config.get('MAIL_USERNAME'),
            current_app.config.get('MAIL_PASSWORD'),
            current_app.config.get('MAIL_FROM'),
        ]
    )


def send_email_message(subject, recipient, body):
    if not is_mail_configured():
        return False

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = current_app.config['MAIL_FROM']
    message['To'] = recipient
    message.set_content(body)

    with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT']) as smtp:
        if current_app.config['MAIL_USE_TLS']:
            smtp.starttls()
        smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        smtp.send_message(message)

    return True


def generate_password_reset_token(user):
    serializer = get_token_serializer()
    return serializer.dumps(user.email, salt=current_app.config['PASSWORD_RESET_SALT'])


def verify_password_reset_token(token):
    serializer = get_token_serializer()
    email = serializer.loads(
        token,
        salt=current_app.config['PASSWORD_RESET_SALT'],
        max_age=current_app.config['PASSWORD_RESET_EXPIRES_MINUTES'] * 60,
    )
    return User.query.filter_by(email=email).first()


def generate_email_verification_token(user):
    serializer = get_token_serializer()
    return serializer.dumps(user.email, salt=current_app.config['EMAIL_VERIFICATION_SALT'])


def verify_email_verification_token(token):
    serializer = get_token_serializer()
    email = serializer.loads(
        token,
        salt=current_app.config['EMAIL_VERIFICATION_SALT'],
        max_age=current_app.config['EMAIL_VERIFICATION_EXPIRES_HOURS'] * 3600,
    )
    return User.query.filter_by(email=email).first()


def send_email_verification(user):
    verification_token = generate_email_verification_token(user)
    verification_link = url_for('verify_email', token=verification_token, _external=True)
    email_body = (
        'Підтвердіть свою пошту для FindMyPet.\n\n'
        f'Перейдіть за посиланням:\n{verification_link}\n\n'
        f'Посилання дійсне {current_app.config["EMAIL_VERIFICATION_EXPIRES_HOURS"]} годин.\n'
        'Якщо ви не створювали акаунт, просто проігноруйте цей лист.'
    )
    send_email_message('FindMyPet - підтвердження пошти', user.email, email_body)


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            flash('Спочатку увійдіть у свій акаунт.')
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapped_view


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            flash('Спочатку увійдіть у свій акаунт.')
            return redirect(url_for('login'))
        if not current_user.is_admin:
            flash('Доступ до адмінки мають лише адміністратори.')
            return redirect(url_for('home'))
        return view_func(*args, **kwargs)

    return wrapped_view
