import os

from flask import Flask

import config
from auth_helpers import get_current_user, is_mail_configured, is_recaptcha_configured
from bootstrap import init_app_data
from extensions import db, get_google_oauth, setup_google_oauth
from routes_auth import register_auth_routes
from routes_site import register_site_routes


app = Flask(__name__)

app.config.update(
    SQLALCHEMY_DATABASE_URI='sqlite:///database.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('FLASK_SECRET_KEY') or config.FLASK_SECRET_KEY or 'secret_key_123',
    UPLOAD_FOLDER='static/uploads',
    GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID') or config.GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET') or config.GOOGLE_CLIENT_SECRET,
    RECAPTCHA_SITE_KEY=os.getenv('RECAPTCHA_SITE_KEY') or getattr(config, 'RECAPTCHA_SITE_KEY', ''),
    RECAPTCHA_SECRET_KEY=os.getenv('RECAPTCHA_SECRET_KEY') or getattr(config, 'RECAPTCHA_SECRET_KEY', ''),
    RECAPTCHA_MIN_SCORE=float(os.getenv('RECAPTCHA_MIN_SCORE') or getattr(config, 'RECAPTCHA_MIN_SCORE', 0.5)),
    MAIL_SERVER=os.getenv('MAIL_SERVER') or getattr(config, 'MAIL_SERVER', ''),
    MAIL_PORT=int(os.getenv('MAIL_PORT') or getattr(config, 'MAIL_PORT', 587)),
    MAIL_USE_TLS=(os.getenv('MAIL_USE_TLS') or str(getattr(config, 'MAIL_USE_TLS', 'true'))).lower() in {'1', 'true', 'yes', 'on'},
    MAIL_USERNAME=os.getenv('MAIL_USERNAME') or getattr(config, 'MAIL_USERNAME', ''),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD') or getattr(config, 'MAIL_PASSWORD', ''),
    MAIL_FROM=os.getenv('MAIL_FROM') or getattr(config, 'MAIL_FROM', getattr(config, 'MAIL_USERNAME', '')),
    PASSWORD_RESET_SALT=os.getenv('PASSWORD_RESET_SALT') or getattr(config, 'PASSWORD_RESET_SALT', 'password-reset-salt'),
    PASSWORD_RESET_EXPIRES_MINUTES=int(
        os.getenv('PASSWORD_RESET_EXPIRES_MINUTES') or getattr(config, 'PASSWORD_RESET_EXPIRES_MINUTES', 30)
    ),
    EMAIL_VERIFICATION_SALT=os.getenv('EMAIL_VERIFICATION_SALT') or getattr(config, 'EMAIL_VERIFICATION_SALT', 'email-verification-salt'),
    EMAIL_VERIFICATION_EXPIRES_HOURS=int(
        os.getenv('EMAIL_VERIFICATION_EXPIRES_HOURS') or getattr(config, 'EMAIL_VERIFICATION_EXPIRES_HOURS', 24)
    ),
)

app.secret_key = app.config['SECRET_KEY']

db.init_app(app)
setup_google_oauth(app)


@app.context_processor
def inject_user():
    current_user = get_current_user()
    return {
        'user': current_user.username if current_user else None,
        'current_user': current_user,
        'google_auth_enabled': get_google_oauth() is not None,
        'recaptcha_enabled': is_recaptcha_configured(),
        'recaptcha_site_key': app.config['RECAPTCHA_SITE_KEY'],
        'mail_configured': is_mail_configured(),
    }


register_auth_routes(app)
register_site_routes(app)
init_app_data(app)


if __name__ == '__main__':
    app.run(debug=True)
