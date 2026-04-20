# FindMyPet

Вебзастосунок на Flask для публікації оголошень про загублених і знайдених домашніх тварин, керування профілем користувача та модерації контенту через адмін-панель.

## Коротко про проєкт

FindMyPet допомагає користувачам:

- створювати оголошення про загублених або знайдених тварин
- переглядати стрічку публікацій
- фільтрувати оголошення за основними параметрами
- коментувати пости
- керувати власним профілем і своїми оголошеннями
- модерувати контент через адміністративну панель

Проєкт побудований на серверному рендерингу Flask, SQLite та невеликому шарі JavaScript для покращення UX.

## Можливості

### Для користувача

- Реєстрація через email і пароль
- Вхід за логіном або email
- Вхід через Google
- Підтвердження email для локальних акаунтів
- Відновлення пароля через пошту
- Редагування профілю та аватара
- Створення, редагування і видалення власних оголошень
- Додавання коментарів до оголошень

### Для стрічки оголошень

- Перегляд усіх актуальних публікацій
- Пошук за ключовим словом
- Фільтрація за:
  - статусом
  - типом тварини
  - локацією
- Перегляд фото у lightbox
- Показ номера телефону по кліку

### Для адміністратора

- Автоматичне створення адміністратора при ініціалізації
- Окрема адмін-панель
- Видалення чужих оголошень

## Технології

- `Python`
- `Flask`
- `Flask-SQLAlchemy`
- `SQLite`
- `Authlib`
- `requests`
- `HTML + Jinja2`
- `CSS`
- `Vanilla JavaScript`

## Структура проєкту

```text
FindMyPet/
├── app.py
├── auth_helpers.py
├── bootstrap.py
├── config.py
├── extensions.py
├── forms.py
├── models.py
├── requirements.txt
├── routes_auth.py
├── routes_site.py
├── static/
│   ├── images/
│   ├── js/
│   │   └── script.js
│   ├── style.css
│   └── uploads/
├── templates/
│   ├── add.html
│   ├── admin.html
│   ├── cabinet.html
│   ├── complete_profile.html
│   ├── edit_pet.html
│   ├── forgot_password.html
│   ├── header.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── resend_verification.html
│   └── reset_password.html
└── instance/
    └── database.db
```

## Архітектура

Проєкт поділено на окремі модулі, щоб код було легше підтримувати:

- [app.py](app.py)  
  Створення Flask-застосунку, конфігурація, підключення модулів і запуск

- [extensions.py](extensions.py)  
  Спільні Flask-розширення: SQLAlchemy і Google OAuth

- [models.py](models.py)  
  Моделі бази даних: `User`, `Pet`, `Comment`

- [auth_helpers.py](auth_helpers.py)  
  Допоміжна логіка: паролі, reCAPTCHA, email, токени, декоратори доступу, робота із сесією

- [routes_auth.py](routes_auth.py)  
  Усі маршрути авторизації: вхід, реєстрація, підтвердження email, скидання пароля, Google OAuth

- [routes_site.py](routes_site.py)  
  Публічна частина сайту, стрічка, коментарі, кабінет, адмінка, CRUD для оголошень

- [bootstrap.py](bootstrap.py)  
  Ініціалізація структури бази, перевірка колонок і створення адміністратора

## Основні сторінки

- `/` — головна сторінка зі стрічкою оголошень
- `/login` — сторінка входу
- `/register` — сторінка реєстрації
- `/forgot-password` — відновлення пароля
- `/cabinet` — особистий кабінет
- `/add` — створення нового оголошення
- `/admin` — панель адміністратора


## Конфігурація

Застосунок спочатку читає значення зі змінних середовища, а якщо їх немає — бере з [config.py](config.py).

Основні параметри:

```text
FLASK_SECRET_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
RECAPTCHA_SITE_KEY
RECAPTCHA_SECRET_KEY
RECAPTCHA_MIN_SCORE
MAIL_SERVER
MAIL_PORT
MAIL_USE_TLS
MAIL_USERNAME
MAIL_PASSWORD
MAIL_FROM
PASSWORD_RESET_SALT
PASSWORD_RESET_EXPIRES_MINUTES
EMAIL_VERIFICATION_SALT
EMAIL_VERIFICATION_EXPIRES_HOURS
```

Приклад:

```python
FLASK_SECRET_KEY = 'your-secret-key'
GOOGLE_CLIENT_ID = 'your-google-client-id'
GOOGLE_CLIENT_SECRET = 'your-google-client-secret'
RECAPTCHA_SITE_KEY = 'your-recaptcha-site-key'
RECAPTCHA_SECRET_KEY = 'your-recaptcha-secret-key'
RECAPTCHA_MIN_SCORE = 0.5
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'your-email@gmail.com'
MAIL_PASSWORD = 'your-app-password'
MAIL_FROM = 'FindMyPet <your-email@gmail.com>'
```

## Адміністратор за замовчуванням

Під час ініціалізації застосунок створює адміністратора, якщо його ще немає:

```text
username: -
password: -
```

Адмін-панель:

```text
/admin
```

## Інтерфейс і UX

У проєкті вже реалізовані невеликі, але корисні покращення інтерфейсу:

- адаптація під десктоп, планшет і телефон
- мобільне меню
- автоматичне зникнення flash-повідомлень
- lightbox для фото тварин
- показ телефону по кнопці
- підтвердження перед небезпечними діями

Основні шаблони:

- [templates/index.html](templates/index.html)
- [templates/login.html](templates/login.html)
- [templates/register.html](templates/register.html)
- [templates/cabinet.html](templates/cabinet.html)
- [templates/admin.html](templates/admin.html)
- [templates/add.html](templates/add.html)
- [templates/edit_pet.html](templates/edit_pet.html)

Основні frontend-файли:

- [static/style.css](static/style.css)
- [static/js/script.js](static/js/script.js)

## Безпека

У поточному стані в [config.py](config.py) зберігаються чутливі значення.  
Для реального розгортання рекомендовано:

- винести секрети в змінні середовища або приватний `.env`
- перевипустити вже засвічені ключі
- вимкнути `debug=True` у production
- не зберігати реальні секрети в Git

## Залежності

Поточний список залежностей із [requirements.txt](requirements.txt):

```text
Flask
Flask-SQLAlchemy
Authlib
requests
```

## Що можна покращити далі

- окрема сторінка детального перегляду оголошення
- кілька фото для одного поста
- приватні повідомлення між користувачами
- інтеграція карти для локацій
- розширені інструменти модерації
- автоматичні тести
- міграції через Flask-Migrate або Alembic

## Статус

Проєкт уже можна використовувати як:

- навчальний вебпроєкт
- курсову або дипломну основу
- portfolio-проєкт на Flask
- базу для подальшого розвитку
