from datetime import datetime

from extensions import db


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
