from flask import Flask, render_template, request, redirect, flash, session, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship

# Инициализация приложения
app = Flask(__name__)
app.secret_key = 'секретный_ключ'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)

# Добавляем фильтры для перевода типа абонемента и дней недели
@app.template_filter('translate_membership_type')
def translate_membership_type(value):
    types = {
        'trial': 'Пробный',
        '8': '8 занятий',
        '12': '12 занятий'
    }
    return types.get(value, value)

@app.template_filter('translate_days')
def translate_days(days_string):
    days_dict = {
        'Mon': 'Понедельник',
        'Tue': 'Вторник',
        'Wed': 'Среда',
        'Thu': 'Четверг',
        'Fri': 'Пятница',
        'Sat': 'Суббота',
        'Sun': 'Воскресенье'
    }
    if days_string:
        days_list = days_string.split(', ')
        return ', '.join([days_dict.get(day, day) for day in days_list])
    return days_string

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth"  # Страница для перенаправления, если пользователь не авторизован

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(100), nullable=False)
    membership = db.relationship('Membership', backref='owner', uselist=False)

    def set_password(self, password):
        """Хеширует пароль перед сохранением"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Проверяет правильность пароля"""
        return bcrypt.check_password_hash(self.password_hash, password)


class Membership(db.Model):
    id = Column(Integer, primary_key=True)
    type = Column(String(50))
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    user_id = Column(Integer, db.ForeignKey('user.id'))
    days = Column(Text)  # Это поле для дней
    time = Column(String(20))

    user = relationship('User', back_populates='membership')

    def __repr__(self):
        return f'<Membership {self.type}>'


# Вспомогательные функции для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Роуты
@app.route('/')
def index():
    return render_template("index.html")


@app.route('/membership', methods=['GET', 'POST'])
@login_required
def membership():
    if request.method == 'POST':
        membership_type = request.form['membership_type']
        selected_days = request.form.getlist('days[]')  # Получаем выбранные дни из формы
        selected_time = request.form['time']  # Получаем выбранное время

        if current_user.membership:
            flash('У вас уже есть активный абонемент!', 'warning')
            return redirect(url_for('membership'))

        # Преобразуем выбранные дни в строку (например, "Mon, Wed, Fri")
        selected_days_str = ', '.join(selected_days)

        # Создание нового абонемента
        new_membership = Membership(
            type=membership_type,
            days=selected_days_str,  # Сохраняем дни как строку
            time=selected_time,
            user_id=current_user.id
        )

        # Настройка даты окончания абонемента
        if membership_type == 'trial':
            new_membership.end_date = datetime.utcnow() + timedelta(days=7)  # Пробный абонемент
        elif membership_type == '8':
            new_membership.end_date = datetime.utcnow() + timedelta(weeks=4)  # 8 занятий
        elif membership_type == '12':
            new_membership.end_date = datetime.utcnow() + timedelta(weeks=6)  # 12 занятий

        # Сохраняем новый абонемент в базе данных
        db.session.add(new_membership)
        db.session.commit()

        flash(f'Вы успешно записались на абонемент "{membership_type}"!', 'success')
        return redirect(url_for('membership'))

    return render_template('membership.html', user=current_user)


@app.route('/cancel-membership', methods=['POST'])
@login_required
def cancel_membership():
    if current_user.membership:
        # Удаляем абонемент
        db.session.delete(current_user.membership)
        db.session.commit()
        flash("Ваш абонемент был успешно отменен.", "success")
        return redirect(url_for('cancel_membership_success'))
    else:
        flash("У вас нет активного абонемента для отмены.", "warning")
        return redirect(url_for('membership'))


@app.route('/cancel-membership-success')
@login_required
def cancel_membership_success():
    return render_template('cancel-membership.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()  # Выход с использованием Flask-Login
    flash("Вы вышли из аккаунта", "info")
    return redirect('/')

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/coaches-schedule')
def schedule():
    return render_template("coaches-schedule.html")

@app.route('/contacts')
def contacts():
    return render_template("contacts.html")


@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated:  # Если пользователь уже авторизован
        return redirect('/membership')  # Перенаправляем на страницу абонемента

    if request.method == 'POST':
        action = request.form['action']
        username = request.form['username']
        password = request.form['password']

        if action == 'register':  # Регистрация пользователя
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash("Пользователь уже существует", "danger")
            else:
                user = User(username=username)
                user.set_password(password)  # Хешируем пароль перед сохранением
                db.session.add(user)
                db.session.commit()
                flash("Регистрация прошла успешно", "success")
                return redirect('/auth')  # После регистрации перенаправляем обратно на форму

        elif action == 'login':  # Вход пользователя
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):  # Проверяем пароль с хешем
                login_user(user)  # Используем login_user для правильной авторизации
                flash(f"Добро пожаловать, {username}!", "success")
                return redirect('/membership')  # Перенаправляем на страницу оформления абонемента
            else:
                flash("Неверный логин или пароль", "danger")

    return render_template('auth.html')

# Создание БД и таблиц
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)