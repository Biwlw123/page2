from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory, abort
import psycopg2
import os
import uuid
from psycopg2.extras import DictCursor
from urllib.parse import urlparse

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', 'your_fallback_secret_key')

# Database connection
def get_db():
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("No DATABASE_URL set in environment variables")
    
    # Render использует postgres://, но psycopg2 требует postgresql://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(
            db_url,
            cursor_factory=DictCursor,
            sslmode='require'  # Для безопасности на Render
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Cannot connect to database. Error: {e}")
        print(f"Connection string was: {db_url.split('@')[0]}@***")
        raise
    except Exception as e:
        print(f"Unexpected database error: {e}")
        raise
# Initialize database
def init_db():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Drop tables if they exist (for development)
        cursor.execute('DROP TABLE IF EXISTS comments CASCADE')
        cursor.execute('DROP TABLE IF EXISTS uploaded_files CASCADE')
        cursor.execute('DROP TABLE IF EXISTS entries CASCADE')

        # Create tables
        cursor.execute('''
            CREATE TABLE entries (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES entries (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE comments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES entries (id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES uploaded_files (id) ON DELETE CASCADE
            )
        ''')

        # Add test user
        cursor.execute('''
            INSERT INTO entries (first_name, last_name, course, university, region, password)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        ''', ('Олег', 'Булавин', 'Курс', 'Университет', 'Регион', 'Oleg2005'))

        conn.commit()
        print("Database initialized successfully")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Database initialization error: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/Forma')
def Forma():
    return render_template('Forma.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.form
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO entries (first_name, last_name, course, university, region, password)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            data['first_name'],
            data['last_name'],
            data['course'],
            data['university'],
            data['region'],
            data['password']
        ))
        conn.commit()
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка регистрации: {str(e)}', 'error')
    finally:
        if conn:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, first_name, last_name FROM entries 
                WHERE first_name = %s AND last_name = %s AND password = %s
            ''', (
                request.form['first_name'],
                request.form['last_name'],
                request.form['password']
            ))
            user = cursor.fetchone()

            if user:
                session.update({
                    'user_id': user['id'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name']
                })

                if user['first_name'] == 'Олег' and user['last_name'] == 'Булавин':
                    return redirect(url_for('developer'))
                return redirect(url_for('dashboard'))
            else:
                flash('Неверные данные для входа', 'error')
        except Exception as e:
            flash(f'Ошибка входа: {str(e)}', 'error')
        finally:
            if conn:
                cursor.close()
                conn.close()
    return render_template('Vxod.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))
    return render_template('Case.html')

@app.route('/solve')
def solve():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.message, c.date_sent, e.first_name, e.last_name
            FROM comments c
            JOIN uploaded_files uf ON c.file_id = uf.id
            JOIN entries e ON c.user_id = e.id
            WHERE uf.user_id = %s
            ORDER BY c.date_sent DESC
        ''', (session['user_id'],))
        file_responses = cursor.fetchall()
        return render_template('RSM.html', file_responses=file_responses)
    except Exception as e:
        flash(f'Ошибка базы данных: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Требуется авторизация'})

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Файл не выбран'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Файл не выбран'})

    # Create uploads directory if not exists
    os.makedirs('uploads', exist_ok=True)

    # Generate unique filename
    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}{os.path.splitext(original_filename)[1]}"
    file_path = os.path.join('uploads', unique_filename)
    file.save(file_path)

    # Save to database
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO uploaded_files (user_id, file_name, file_path)
            VALUES (%s, %s, %s)
        ''', (session['user_id'], original_filename, file_path))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Файл загружен'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/proverka')
def proverka():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT uf.id, uf.file_name, uf.file_path, uf.date_uploaded, 
                   e.first_name, e.last_name
            FROM uploaded_files uf
            JOIN entries e ON uf.user_id = e.id
            WHERE uf.user_id = %s
        ''', (session['user_id'],))
        files = cursor.fetchall()
        return render_template('Proverka.html', files=files)
    except Exception as e:
        flash(f'Ошибка базы данных: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Требуется авторизация'})

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO comments (user_id, file_id, message)
            VALUES (%s, %s, %s)
        ''', (
            session['user_id'],
            request.form['file_id'],
            request.form['message']
        ))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Отзыв отправлен'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/developer')
def developer():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get users with file counts
        cursor.execute('''
            SELECT e.id, e.first_name, e.last_name, e.course, 
                   e.university, e.region, e.date_created,
                   COUNT(uf.id) as file_count
            FROM entries e
            LEFT JOIN uploaded_files uf ON e.id = uf.user_id
            GROUP BY e.id
            ORDER BY e.date_created DESC
        ''')
        users = cursor.fetchall()
        
        # Get all files
        cursor.execute('''
            SELECT uf.id, uf.file_name, uf.date_uploaded, 
                   e.id as user_id, e.first_name, e.last_name, e.course
            FROM uploaded_files uf
            JOIN entries e ON uf.user_id = e.id
            ORDER BY uf.date_uploaded DESC
        ''')
        files = cursor.fetchall()
        
        return render_template('Developer.html', users=users, files=files)
    except Exception as e:
        flash(f'Ошибка базы данных: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/download/<filename>')
def download_file(filename):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT file_path FROM uploaded_files WHERE file_name = %s
        ''', (filename,))
        file_record = cursor.fetchone()

        if not file_record:
            flash('Файл не найден', 'error')
            return redirect(url_for('developer'))

        file_path = file_record['file_path']
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)

        if not os.path.exists(file_path):
            flash('Файл не найден на сервере', 'error')
            return redirect(url_for('developer'))

        return send_from_directory(
            directory=directory,
            path=filename,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('developer'))
    finally:
        if conn:
            cursor.close()
            conn.close()

# Static pages
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

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('login'))

@app.route('/keep_session')
def keep_session():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите', 'error')
        return redirect(url_for('login'))

    if request.referrer and 'Case.html' in request.referrer:
        return redirect(url_for('index'))
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')