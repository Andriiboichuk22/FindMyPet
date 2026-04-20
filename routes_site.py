from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from auth_helpers import (
    admin_required,
    get_current_user,
    is_mail_configured,
    login_required,
    normalize_email,
    save_uploaded_file,
    send_email_verification,
    set_logged_in_user,
)
from extensions import db
from models import Comment, Pet, User


def register_site_routes(app):
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
            flash('Відгук не може бути порожнім.')
            return redirect(url_for('home', **request.args))

        comment = Comment(
            content=content,
            pet_id=pet.id,
            user_id=current_user.id,
        )
        db.session.add(comment)
        db.session.commit()
        flash('Відгук успішно додано.')
        return redirect(url_for('home', **request.args))

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
            flash('Оголошення успішно опубліковано.')
            return redirect(url_for('home'))

        return render_template('add.html', profile_user=current_user)

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
                flash('Вкажіть email.')
                return redirect(url_for('cabinet'))

            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user and existing_user.id != current_user.id:
                flash('Такий логін уже зайнятий.')
                return redirect(url_for('cabinet'))

            existing_email_user = User.query.filter_by(email=new_email).first()
            if existing_email_user and existing_email_user.id != current_user.id:
                flash('Користувач із таким email уже існує.')
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
                        flash('Email оновлено, але лист для підтвердження не вдалося надіслати.')
                        return redirect(url_for('cabinet'))
                set_logged_in_user(current_user)
                if current_user.auth_provider == 'local' and email_changed:
                    flash('Профіль оновлено. Підтвердьте нову email-адресу через лист.')
                else:
                    flash('Профіль успішно оновлено.')
            except IntegrityError:
                db.session.rollback()
                flash('Логін або email уже зайняті.')

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
            flash('Ви не можете редагувати це оголошення.')
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
            flash('Оголошення успішно оновлено.')
            return redirect(url_for('cabinet'))

        return render_template('edit_pet.html', pet=pet, profile_user=current_user)

    @app.route('/pets/<int:pet_id>/delete', methods=['POST'])
    @login_required
    def delete_pet(pet_id):
        current_user = get_current_user()
        pet = Pet.query.get_or_404(pet_id)

        if pet.user_id != current_user.id and not current_user.is_admin:
            flash('Ви не можете видалити це оголошення.')
            return redirect(url_for('cabinet'))

        db.session.delete(pet)
        db.session.commit()
        flash('Оголошення успішно видалено.')

        if current_user.is_admin and pet.user_id != current_user.id:
            return redirect(url_for('admin_panel'))
        return redirect(url_for('cabinet'))

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))
