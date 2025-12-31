from flask import Flask
import flask
from stravalib.client import Client
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy
import datetime
import sys
import os
from waitress import serve

# Try to import local secrets, fall back to environment variables
try:
    import secrets as local_secrets
    STRAVA_CLIENT_ID = getattr(local_secrets, 'client_id', None)
    STRAVA_CLIENT_SECRET = getattr(local_secrets, 'api_key', None)
    FLASK_SECRET_KEY = getattr(local_secrets, 'secret_key', 'dev-secret-key')
    DEFAULT_URL = getattr(local_secrets, 'default_url', 'http://localhost:5001')
except ImportError:
    local_secrets = None
    STRAVA_CLIENT_ID = None
    STRAVA_CLIENT_SECRET = None
    FLASK_SECRET_KEY = 'dev-secret-key'
    DEFAULT_URL = 'http://localhost:5001'

# Environment variables override local secrets (for AWS/Docker deployment)
STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', STRAVA_CLIENT_ID)
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', STRAVA_CLIENT_SECRET)
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', FLASK_SECRET_KEY)
DEFAULT_URL = os.environ.get('DEFAULT_URL', DEFAULT_URL)

# Convert client_id to int if it's a string
if STRAVA_CLIENT_ID and isinstance(STRAVA_CLIENT_ID, str):
    STRAVA_CLIENT_ID = int(STRAVA_CLIENT_ID)

serverURL = DEFAULT_URL

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Use DATABASE_URL from environment (for Docker/AWS) or fallback to local
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://postgres:postgres@localhost/strava'
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Total days in the grid (366 to include leap day)
GRID_TOTAL = 366

class GreensModel(db.Model):
	__tablename__ = 'greens'
	
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String())
	num = db.Column(db.Integer)
	grid_count = db.Column(db.Integer, default=0)
	lastupdate = db.Column(sqlalchemy.types.TIMESTAMP)

	def __init__(self, name, id, greens, lastupdate, grid_count=0):
		self.name = name
		self.id = id
		self.num = greens
		self.grid_count = grid_count
		self.lastupdate = lastupdate
	
	def __repr__(self):
		return f"<Green {self.name}>"

# Create tables on startup
with app.app_context():
	try:
		print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
		db.create_all()
		print("Database tables created successfully")
	except Exception as e:
		print(f"Error creating database tables: {e}")

def get_grid_days(client, segments):
	"""
	Fetch all segment efforts and return the set of unique (month, day) tuples.
	This represents the "grid" - unique days of the year summited.
	"""
	unique_days = set()
	
	for segment_id in segments:
		try:
			# Get all efforts for this segment by the authenticated athlete
			efforts = client.get_segment_efforts(segment_id)
			for effort in efforts:
				# Extract month and day from the effort start date
				start_date = effort.start_date_local
				if start_date:
					day_tuple = (start_date.month, start_date.day)
					unique_days.add(day_tuple)
		except Exception as e:
			print(f"Error fetching efforts for segment {segment_id}: {e}")
			continue
	
	return unique_days

@app.route("/")
def main_page():
	sqlQuery = GreensModel.query.order_by(GreensModel.num.desc()).all()
	people = [
		{	"id": person.id,
			"greens": person.num,
			"grid_count": person.grid_count or 0,
			"name": person.name,
			"lastupdate": (datetime.datetime.utcnow() - person.lastupdate).days
		} for person in sqlQuery]
	if flask.session.get("access_token"):
		grid_count = flask.session.get("grid_count", 0)
		grid_percent = round((grid_count / GRID_TOTAL) * 100, 1)
		return flask.render_template("index.html", 
			greens=flask.session.get("greens"), 
			name=flask.session.get("name"), 
			id=flask.session.get("id"), 
			people=people,
			grid_count=grid_count,
			grid_total=GRID_TOTAL,
			grid_percent=grid_percent)		
	else:
		client = Client()
		authorize_url = client.authorization_url(client_id=STRAVA_CLIENT_ID, redirect_uri=serverURL+'/authorized',scope="activity:read_all")
		return flask.render_template("index.html", url=authorize_url, people=people)
	
@app.route("/authorized", methods=["GET"])
def authorize_page():
	if flask.request.args.get('error'):
		return flask.redirect("/")
	client = Client()
	code = flask.request.args.get('code') # or whatever your framework does
	token_response = client.exchange_code_for_token(client_id=STRAVA_CLIENT_ID, client_secret=STRAVA_CLIENT_SECRET, code=code)
	flask.session['access_token'] = token_response['access_token']
	flask.session['refresh_token'] = token_response['refresh_token']
	flask.session['expires_at'] = token_response['expires_at']
	client.access_token = token_response['access_token']
	client.refresh_token = token_response['refresh_token']
	client.expires_at = token_response['expires_at']
	athlete = client.get_athlete()
	name = athlete.firstname + " " + athlete.lastname
	flask.session['name'] = name
	flask.session['id'] = athlete.id
	return flask.redirect("/greens")

@app.route("/greens", methods=["GET"])
def greens_page():
	if flask.session.get("access_token"):
		client = Client()
		client.access_token = flask.session.get("access_token")
		client.refresh_token = flask.session.get('refresh_token')
		client.expires_at = flask.session.get('expires_at')
		
		segments = ["30545810", "30546062", "30546055", "7492562"]
		
		# Get total summit count from segment stats
		greens = 0
		for segment in segments:
			s = client.get_segment(segment)
			greens += s.athlete_segment_stats.effort_count
		flask.session['greens'] = greens
		
		# Calculate grid count (unique days of the year summited)
		unique_days = get_grid_days(client, segments)
		grid_count = len(unique_days)
		flask.session['grid_count'] = grid_count
		
		print(f"Total summits: {greens}, Grid days: {grid_count}/{GRID_TOTAL}")
		
		person = GreensModel.query.get(flask.session.get('id'))
		if person:
			person.name = flask.session.get('name')
			person.num = greens
			person.grid_count = grid_count
			person.lastupdate = datetime.datetime.utcnow()
			db.session.add(person)
			db.session.commit()
		else:
			newPerson = GreensModel(
				name=flask.session.get('name'), 
				id=flask.session.get('id'), 
				greens=greens, 
				grid_count=grid_count,
				lastupdate=datetime.datetime.utcnow()
			)
			db.session.add(newPerson)
			db.session.commit()
	return flask.redirect("/")

@app.route("/logout")
def logout_page():
	flask.session.pop('access_token', None)
	flask.session.pop('name', None)
	flask.session.pop('refresh_token', None)
	flask.session.pop('id', None)
	flask.session.pop('greens', None)
	flask.session.pop('grid_count', None)
	return flask.redirect("/")

@app.route('/favicon.ico')
def favicon():
	return flask.send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/media/<path:filename>')
def media(filename):
	return flask.send_from_directory(os.path.join(app.root_path, 'media'), filename)
	
	
def create_app():
   return app

if __name__ == '__main__':
	if len(sys.argv) == 2:
		serverURL = sys.argv[1]
	print("Website starting at: "+serverURL)
	
	# Create database tables if they don't exist
	with app.app_context():
		db.create_all()
		print("Database tables initialized")
	
	# Listen on 0.0.0.0 to be accessible from outside Docker container
	serve(app, host='0.0.0.0', port=5000)

