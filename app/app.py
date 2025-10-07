#import the libraries/modules
from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import json
from datetime import datetime

import os
import dotenv

#Initialize Flask app
app = Flask(__name__)


#Call and configure variables from .env/redis
DB_HOST = os.getenv('DATABASE_HOST', 'localhost')
DB_PORT = os.getenv('DATABASE_PORT', '5432')
DB_NAME = os.getenv('DATABASE_NAME', 'taskdb')
DB_USER = os.getenv('DATABASE_USER', 'postgres')
DB_PASSWORD = os.getenv('DATABASE_PASSWORD', 'password')


REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

APP_NAME = os.getenv('APP_NAME', 'DevOps Task Manager')
APP_ENV = os.getenv('APP_ENV', 'development')

#Database connection
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )
    return conn

#Redis connection for caching
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False
    print("Redis not available, running without cache")


# Initialize database
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Define Flask app routes
@app.route('/')
def index():
    # Try cache first
    if REDIS_AVAILABLE:
        cached_tasks = redis_client.get('tasks')
        if cached_tasks:
            tasks = json.loads(cached_tasks)
            return render_template('index.html', tasks=tasks, app_name=APP_NAME, 
                                 env=APP_ENV, from_cache=True)
    
    # Get from database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM tasks ORDER BY created_at DESC')
    tasks = cur.fetchall()
    cur.close()
    conn.close()

    # Cache for 60 seconds
    if REDIS_AVAILABLE:
        redis_client.setex('tasks', 60, json.dumps(tasks, default=str))
    
    return render_template('index.html', tasks=tasks, app_name=APP_NAME, 
                         env=APP_ENV, from_cache=False)


@app.route('/add', methods=['POST'])
def add_task():
    title = request.form.get('title')
    description = request.form.get('description', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO tasks (title, description) VALUES (%s, %s)',
        (title, description)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    # Invalidate cache
    if REDIS_AVAILABLE:
        redis_client.delete('tasks')
    
    return redirect(url_for('index'))

@app.route('/complete/<int:task_id>')
def complete_task(task_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s',
        ('completed', datetime.now(), task_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    # Invalidate cache
    if REDIS_AVAILABLE:
        redis_client.delete('tasks')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    # Invalidate cache
    if REDIS_AVAILABLE:
        redis_client.delete('tasks')
    
    return redirect(url_for('index'))

@app.route('/health')
def health():
    health_status = {
        'status': 'healthy',
        'app': APP_NAME,
        'environment': APP_ENV,
        'database': 'connected',
        'redis': 'connected' if REDIS_AVAILABLE else 'not available',
        'pod': os.getenv('HOSTNAME', 'unknown')
    }
    
    # Check database
    try:
        conn = get_db_connection()
        conn.close()
    except:
        health_status['database'] = 'disconnected'
        health_status['status'] = 'unhealthy'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code

# Metrics endpoint (for monitoring)
@app.route('/metrics')
def metrics():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) as total FROM tasks')
    total_tasks = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as completed FROM tasks WHERE status = 'completed'")
    completed_tasks = cur.fetchone()['completed']
    
    cur.close()
    conn.close()
    
    return jsonify({
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': total_tasks - completed_tasks,
        'cache_enabled': REDIS_AVAILABLE
    })

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=(APP_ENV == 'development'))
