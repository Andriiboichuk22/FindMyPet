from flask_sqlalchemy import SQLAlchemy

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None


db = SQLAlchemy()
oauth = None
google_oauth = None


def setup_google_oauth(app):
    global oauth, google_oauth

    client_id = app.config.get('GOOGLE_CLIENT_ID')
    client_secret = app.config.get('GOOGLE_CLIENT_SECRET')
    if OAuth is None or not client_id or not client_secret:
        google_oauth = None
        return

    oauth = OAuth(app)
    google_oauth = oauth.register(
        name='google',
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid profile email'},
    )


def get_google_oauth():
    return google_oauth
