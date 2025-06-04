from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory, abort
import sqlite3
import os
import uuid

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'your_secret_key'  # Replace with your secret key
def get_db():
    db = sqlite3.connect('instance/data.db', check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")  # Включаем WAL для лучшей конкурентности
    return db
# Initialize the database
def init_db():
    # Убедимся, что папка существует
    if not os.path.exists('instance'):
        os.makedirs('instance')
    
    # Подключаемся к базе данных (создаст новый файл, если не существует)
    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()

    # Удаляем таблицы, если они существуют (для чистой инициализации)
    cursor.execute('DROP TABLE IF EXISTS entries')
    cursor.execute('DROP TABLE IF EXISTS uploaded_files')
    cursor.execute('DROP TABLE IF EXISTS comments')

    # Создаем таблицы заново
    cursor.execute('''
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            course TEXT NOT NULL,
            university TEXT NOT NULL,
            region TEXT NOT NULL,
            password TEXT NOT NULL,
            date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES entries (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES entries (id),
            FOREIGN KEY (file_id) REFERENCES uploaded_files (id)
        )
    ''')

    # Добавляем тестового пользователя
    try:
        cursor.execute('''
            INSERT INTO entries (first_name, last_name, course, university, region, password)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Олег', 'Булавин', 'Курс', 'Университет', 'Регион', 'Oleg2005'))
    except sqlite3.IntegrityError:
        pass  # Пользователь уже существует

    conn.commit()
    conn.close()
    print("База данных успешно инициализирована")
# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/Forma')
def Forma():
    return render_template('Forma.html')

@app.route('/submit', methods=['POST'])
def submit():
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    course = request.form['course']
    university = request.form['university']
    region = request.form['region']
    password = request.form['password']

    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO entries (first_name, last_name, course, university, region, password)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (first_name, last_name, course, university, region, password))
    conn.commit()
    conn.close()

    flash('Регистрация успешна! Теперь вы можете войти.', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        password = request.form['password']
        conn = sqlite3.connect('instance/data.db')  
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, first_name, last_name FROM entries WHERE first_name = ? AND last_name = ? AND password = ?
        ''', (first_name, last_name, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['first_name'] = user[1]
            session['last_name'] = user[2]

            if user[1] == 'Олег' and user[2] == 'Булавин':
                return redirect(url_for('developer'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Неверные данные для входа. Проверьте имя, фамилию и пароль.', 'error')
            return redirect(url_for('login'))

    return render_template('Vxod.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    return render_template('Case.html')

@app.route('/solve')
def solve():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']

    try:
        conn = sqlite3.connect('instance/data.db')
        cursor = conn.cursor()

        # Получаем все отзывы для файлов текущего пользователя
        cursor.execute('''
            SELECT c.message, c.date_sent, e.first_name, e.last_name
            FROM comments c
            JOIN uploaded_files uf ON c.file_id = uf.id
            JOIN entries e ON c.user_id = e.id
            WHERE uf.user_id = ?
            ORDER BY c.date_sent DESC
        ''', (user_id,))
        file_responses = cursor.fetchall()

        conn.close()

    except sqlite3.Error as e:
        flash(f'Ошибка базы данных: {e}', 'error')
        return redirect(url_for('dashboard'))

    return render_template('RSM.html', file_responses=file_responses)

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Пожалуйста, войдите.'})

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Файл не выбран.'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Файл не выбран.'})

    # Создаем папку uploads, если ее нет
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    # Генерируем уникальное имя файла, но сохраняем оригинальное в БД
    original_filename = secure_filename(file.filename)
    file_extension = os.path.splitext(original_filename)[1]
    unique_filename = f'{uuid.uuid4()}{file_extension}'
    file_path = os.path.join('uploads', unique_filename)

    # Сохраняем файл
    file.save(file_path)

    # Сохраняем информацию о файле в БД
    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO uploaded_files (user_id, file_name, file_path)
        VALUES (?, ?, ?)
    ''', (session['user_id'], original_filename, file_path))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Файл успешно загружен!'})
@app.route('/proverka')
def proverka():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']

    try:
        conn = sqlite3.connect('instance/data.db')
        cursor = conn.cursor()

        # Get all uploaded files for the user
        cursor.execute('''
            SELECT uploaded_files.id, uploaded_files.file_name, uploaded_files.file_path, uploaded_files.date_uploaded, entries.first_name, entries.last_name
            FROM uploaded_files
            JOIN entries ON uploaded_files.user_id = entries.id
            WHERE uploaded_files.user_id = ?
        ''', (user_id,))
        files = cursor.fetchall()

        conn.close()

    except sqlite3.Error as e:
        flash(f'Ошибка базы данных: {e}', 'error')
        return redirect(url_for('dashboard'))

    return render_template('Proverka.html', files=files)

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Пожалуйста, войдите.'})

    file_id = request.form['file_id']
    message = request.form['message']

    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()
    
    # Сохраняем отзыв в базе данных
    cursor.execute('''
        INSERT INTO comments (user_id, file_id, message)
        VALUES (?, ?, ?)
    ''', (session['user_id'], file_id, message))
    
    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': 'Отзыв успешно отправлен!'
    })

@app.route('/developer')
def developer():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT uf.id, uf.file_name, uf.date_uploaded, 
               e.first_name, e.last_name, uf.file_name, e.course
        FROM uploaded_files uf
        JOIN entries e ON uf.user_id = e.id
        ORDER BY uf.date_uploaded DESC
    ''')
    files = cursor.fetchall()
    
    conn.close()

    return render_template('Developer.html', files=files)

@app.route('/download/<filename>')
def download_file(filename):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    # Получаем реальный путь к файлу из базы данных
    conn = sqlite3.connect('instance/data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM uploaded_files WHERE file_name = ?', (filename,))
    file_record = cursor.fetchone()
    conn.close()

    if not file_record:
        flash('Файл не найден в базе данных.', 'error')
        return redirect(url_for('developer'))

    file_path = file_record[0]
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    try:
        # Проверяем существование файла
        if not os.path.exists(file_path):
            flash('Файл не найден на сервере.', 'error')
            return redirect(url_for('developer'))

        return send_from_directory(
            directory=directory,
            path=filename,
            as_attachment=True,
            download_name=filename  # Имя файла для скачивания
        )
    except FileNotFoundError:
        abort(404)
@app.route('/VTB.html')
def vtb():
    return render_template('VTB.html')
@app.route('/RSM.html')
def RSM():
    return render_template('RSM.html')
@app.route('/RosAtom.html')
def ROSATOM():
    return render_template('RosAtom.html')
@app.route('/KAR.html')
def KAR():
    return render_template('KAR.html')

@app.route('/Case.html')
def Case():
    return render_template('Case.html')
@app.route('/CPM.html')
def CPM():
    return render_template('CPM.html')
# Route for logging out
@app.route('/logout')
def logout():
    # Remove user_id from the session
    session.pop('user_id', None)
    session.pop('first_name', None)
    session.pop('last_name', None)
    # Redirect the user to the login page
    flash('Вы успешно вышли из системы.', 'success')
    return redirect(url_for('login'))

# Route for keeping the session
@app.route('/keep_session')
def keep_session():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите.', 'error')
        return redirect(url_for('login'))

    # Get the referrer URL
    referrer = request.referrer
    print(f"Referrer: {referrer}")  # Add this line for debugging

    # Check the referrer and redirect accordingly
    if referrer and 'Case.html' in referrer:
        return redirect(url_for('index'))
    else:
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
