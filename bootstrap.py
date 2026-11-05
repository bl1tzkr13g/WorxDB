"""Initialize once before starting multiple server workers."""
import os
from app import init_db, engine
init_db()
engine.dispose()
os.execvp('gunicorn', ['gunicorn','--bind','0.0.0.0:8080','--workers','2','--timeout','120','app:app'])
