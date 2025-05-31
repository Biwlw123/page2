import sqlite3

def view_entries():
    conn = sqlite3.connect('data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM entries')
    rows = cursor.fetchall()

    for row in rows:
        print(row)

    conn.close()

view_entries()