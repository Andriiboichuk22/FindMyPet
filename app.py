from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask import session, flash
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)  

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER  
app.secret_key = "secret_key_123"
db = SQLAlchemy(app)

# МОДЕЛЬ
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(50), nullable=False)   # Зниклий / Знайдений
    animal_type = db.Column(db.String(50))              # Пес / Кіт
    breed = db.Column(db.String(100))                   # Порода
    age = db.Column(db.String(50))                      # Вік

    location = db.Column(db.String(100))                # Місто
    date = db.Column(db.String(50))                     # Дата

    phone = db.Column(db.String(20))                    # Телефон
    photo = db.Column(db.String(200))                   # шлях до фото

# ГОЛОВНА СТОРІНКА
@app.route('/')
def home():
    pets = Pet.query.all()
    return render_template(
        'index.html',
        pets=pets,
        user=session.get('username')
    )


# ДОДАВАННЯ (GET + POST)
@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':

        file = request.files['photo']
        filename = ""

        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        pet = Pet(
            title=request.form['title'],
            description=request.form['description'],
            status=request.form['status'],

            animal_type=request.form['animal_type'],
            breed=request.form['breed'],
            age=request.form['age'],

            location=request.form['location'],
            date=request.form['date'],
            phone=request.form['phone'],

            photo=filename
        )

        db.session.add(pet)
        db.session.commit()

        return redirect('/')

    return render_template('add.html')


# ЛОГІН
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

#Реєстрація
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()

        return redirect('/login')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ЗАПУСК
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
