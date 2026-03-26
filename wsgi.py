import sys
import os

# ── Change this path to wherever you uploaded your project ──
project_home = '/home/codecure/codecure'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Tell Flask to find the DB in the right place
os.chdir(project_home)

from app import app, init_db
init_db()  # creates DB + seeds demo data on first run

application = app
