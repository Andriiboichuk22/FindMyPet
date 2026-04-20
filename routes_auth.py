import secrets

from flask import flash, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from auth_helpers import (
    generate_email_verification_token,
    generate_password_reset_token,
    generate_unique_username,
    get_current_user,
    hash_password,
    is_mail_configured,
    login_required,
    normalize_email,
    send_email_message,
    send_email_verification,
    set_logged_in_user,
    validate_password_strength,
    validate_recaptcha_token,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
)
from extensions import db, get_google_oauth
from models import User


def register_auth_routes(app):
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

            flash('Невірний логін або пароль.')

        return render_template('login.html')

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = normalize_email(request.form['email'])

            if not email:
                flash('Вкажіть email для відновлення пароля.')
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
                    f'Посилання дійсне {app.config["PASSWORD_RESET_EXPIRES_MINUTES"]} хвилин.\n'
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
                flash('Вкажіть email.')
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
                flash('Паролі не збігаються.')
                return render_template('reset_password.html', token=token)

            user.password = hash_password(password)
            db.session.commit()
            flash('Пароль оновлено. Тепер увійдіть з новим паролем.')
            return redirect(url_for('login'))

        return render_template('reset_password.html', token=token)

    @app.route('/login/google')
    def login_google():
        google_oauth = get_google_oauth()
        if google_oauth is None:
            flash('Google-вхід ще не налаштований. Додайте GOOGLE_CLIENT_ID і GOOGLE_CLIENT_SECRET.')
            return redirect(url_for('login'))

        redirect_uri = url_for('google_callback', _external=True)
        nonce = secrets.token_urlsafe(16)
        session['google_nonce'] = nonce
        return google_oauth.authorize_redirect(redirect_uri, nonce=nonce)

    @app.route('/auth/google/callback')
    def google_callback():
        google_oauth = get_google_oauth()
        if google_oauth is None:
            flash('Google-вхід недоступний.')
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

        flash('Вхід через Google виконано успішно.')
        return redirect(url_for('home'))

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
                flash('Вкажіть email.')
                return render_template('register.html')

            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Користувач із таким логіном уже існує.')
                return render_template('register.html')

            existing_email_user = User.query.filter_by(email=email).first()
            if existing_email_user:
                flash('Користувач із таким email уже існує.')
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
                flash('Логін або email уже зайняті.')
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
                flash('Оберіть публічний логін.')
                return render_template('complete_profile.html', profile_user=current_user)

            existing_user = User.query.filter_by(username=username).first()
            if existing_user and existing_user.id != current_user.id:
                flash('Такий логін уже зайнятий.')
                return render_template('complete_profile.html', profile_user=current_user)

            current_user.username = username
            current_user.phone = phone
            current_user.is_username_auto = False
            db.session.commit()

            set_logged_in_user(current_user)
            flash('Профіль успішно збережено.')
            return redirect(url_for('cabinet'))

        return render_template('complete_profile.html', profile_user=current_user)
