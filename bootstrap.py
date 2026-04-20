import os

from sqlalchemy import text

from auth_helpers import hash_password
from extensions import db
from models import User


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
        admin_user = User.query.filter_by(email='admin@findmypet.local').first()

    if admin_user:
        admin_user.username = 'admin'
        admin_user.is_admin = True
        admin_user.email = admin_user.email or 'admin@findmypet.local'
        admin_user.auth_provider = admin_user.auth_provider or 'local'
        admin_user.is_username_auto = False
        admin_user.is_email_verified = True
        admin_user.password = hash_password('admin')
    else:
        admin_user = User(
            username='admin',
            password=hash_password('admin'),
            email='admin@findmypet.local',
            auth_provider='local',
            is_email_verified=True,
            is_username_auto=False,
            is_admin=True,
        )
        db.session.add(admin_user)

    db.session.commit()


def init_app_data(app):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
        ensure_user_columns()
        ensure_admin_user()
