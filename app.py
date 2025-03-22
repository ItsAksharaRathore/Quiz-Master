from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import matplotlib
matplotlib.use('Agg')  # Ensure non-GUI backend



from models import db, User
from config import Config

# Initialize Flask app
app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
# app.config['SECRET_KEY'] = 'your-secret-key-here' 
app.config.from_object(Config)

# Initialize the imported db with your app
db.init_app(app)

# Initialize extensions

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Admin creation function
def create_admin():
    with app.app_context():
        admin = User.query.filter_by(username='admin@gmail.com').first()
        if not admin:
            admin = User(
                username='admin@gmail.com',
                full_name='Quiz Master Admin',
                is_admin=True
            )
            admin.set_password('admin123')  # Change this in production
            db.session.add(admin)
            db.session.commit()

# Main execution
if __name__ == '__main__':
    from routes import *
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=True)