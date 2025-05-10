# Importing dependencies
from flask import Flask, render_template, redirect, jsonify, request, session as flask_session, flash, url_for

import requests
import urllib
import json

import os, joblib, datetime
import numpy as np
import pandas as pd

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

# Functions to search Spotify
def search_spotify(sp, song_name):
    """
    Search Spotify for tracks and prepare track data.
    """
    query = song_name
    try:
        track_list = []
        results = sp.search(q=query, type="track")
        tracks = results["tracks"]["items"]
        # print(tracks)
        track_list = []
        for track in tracks:
            track_id = track['id']
            track_list.append(track_id)
            # print(track_id)
        return track_list

    except Exception as e:
        print("We didn't get that. Try again!")
        return redirect("/search")

# Function to extract audio features for a given track ID
def extract_track_audio_features(sp, track_id):
    """
    Input: 
    Takes track id as input 

    Output:
    Returns a list of track features in the following format:
    ['popularity', 'duration_ms', 'explicit', 'danceability', 'energy','key', 'loudness', 'mode', 
    'speechiness', 'acousticness','instrumentalness', 'liveness', 'valence', 'tempo']
    """
    train_df = pd.read_csv("final_dataset.csv")
    scaler  = joblib.load("scaler.save")

    if track_id in np.array(train_df['track_id']):
        # This data is already scaled and we can directly work with it
        return list(train_df.loc[train_df['track_id'] == track_id].iloc[0])[1:]

    features = []
    track_audio_features = sp.audio_features(track_id)[0]
    features.append(sp.track(track_id)['popularity'])
    features.append(track_audio_features['duration_ms'])
    features.append(sp.track(track_id)['explicit'])
    features.append(track_audio_features['danceability'])
    features.append(track_audio_features['energy'])
    features.append(track_audio_features['key'])
    features.append(track_audio_features['loudness'])
    features.append(track_audio_features['mode'])
    features.append(track_audio_features['speechiness'])
    features.append(track_audio_features['acousticness'])
    features.append(track_audio_features['instrumentalness'])
    features.append(track_audio_features['liveness'])
    features.append(track_audio_features['valence'])
    features.append(track_audio_features['tempo'])
    return list(scaler.transform([features]))


def get_recommendations(sp, track_id):
    train_df = pd.read_csv("final_dataset.csv")
    recommender = joblib.load("recommender.pkl")

    track_features = extract_track_audio_features(sp, track_id)
    track_features = np.array(track_features).reshape(1, -1)
    _, indices = recommender.kneighbors(track_features, return_distance = True)
    recommender_track_ids = train_df.iloc[indices[0]]['track_id'].values
    recommender_track_ids = list(recommender_track_ids)

    if track_id in recommender_track_ids:
        recommender_track_ids.remove(track_id)
    else:
        recommender_track_ids.remove(recommender_track_ids[-1])
    print(list(recommender_track_ids))
    return(list(recommender_track_ids))

# Initialising the Flask app
app = Flask(__name__)

# Initialising the secret keys
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
app.secret_key = os.getenv("FLASK_SECRET_KEY")

REDIRECT_URI = 'https://musicrecs-ouce.onrender.com/callback' #TODO: Change this at the time of deployment
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'
scope = 'user-read-private, user-read-email'

# Defining app routes for the Flask apps
@app.route('/')
def home():
    return render_template("home.html")

@app.route('/login')
def login():
    scope = 'user-read-private user-read-email user-top-read'
    params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': scope
    }

    auth_url = f'{AUTH_URL}?{urllib.parse.urlencode(params)}'
    return redirect(auth_url)

@app.route('/callback')
def callback():
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})
    
    if 'code' in request.args:
        req_body = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }

    response = requests.post(TOKEN_URL, data = req_body)
    token_info = response.json()

    # print("Here is the token_info: ")
    # print(token_info)

    flask_session['access_token'] = token_info['access_token']
    flask_session['refresh_token'] = token_info['refresh_token']
    flask_session['expires_at'] = datetime.datetime.now().timestamp() + token_info['expires_in']
    # print(f"Here is the access token:\n{flask_session["access_token"]}")

    return redirect("/search")

@app.route("/search", methods = ["GET", "POST"])
def search():
    access_token = flask_session.get('access_token')
    song_name = request.args.get('song_name')

    if access_token:
        sp = Spotify(auth = access_token)

        if request.method == "POST":
            song_name = request.form.get('song_name')
            track_list = search_spotify(sp, song_name) # a list containing the relevant track IDs
            
            tracks_info = []
        
            for track_id in track_list:
                track = sp.track(track_id)
                track_name = track['name']
                track_artist = track['album']['artists'][0]['name']
                track_link = f'https://open.spotify.com/track/{track_id}'
                track_image_url = track['album']['images'][0]['url']
                
                # Add track info to the list
                tracks_info.append({
                    'name': track_name,
                    'artist': track_artist,
                    'link': track_link,
                    'image_url': track_image_url
                })
            
            return render_template("confirm.html", tracks = tracks_info)

        return render_template("search.html")
    
    else:
        return redirect("/refresh-token")

@app.route("/recommendations", methods = ["GET", "POST"])
def recommend():
    access_token = flask_session.get('access_token')

    if access_token:
        sp = Spotify(auth = access_token)
        track_id = request.args.get('track_id')
        track_id = track_id.replace("https://open.spotify.com/track/", "")
        
        track_ids = get_recommendations(sp, track_id)
        del track_id

        tracks_info = []
        for track_id in track_ids:
            track = sp.track(track_id)
            track_name = track['name']
            track_artist = track['album']['artists'][0]['name']
            track_link = f'https://open.spotify.com/track/{track_id}'
            track_image_url = track['album']['images'][0]['url']
            
            # Add track info to the list
            tracks_info.append({
                'name': track_name,
                'artist': track_artist,
                'link': track_link,
                'image_url': track_image_url
            })

        return render_template("recommendations.html", tracks = tracks_info)


# @app.route("/search_confirm", methods = ["GET", "POST"])
# def search_confirm():
#     song_name = request.args.get('song_name')
#     access_token = flask_session.get('access_token')
#     if access_token:
#         sp = Spotify(auth=access_token)
#         tracks_data = search_spotify(sp, song_name)
#         return render_template("confirm.html", tracks=tracks_data, song_name=song_name)
#     else:
#         return redirect("/refresh-token")

@app.route("/refresh-token")
def refresh_token():
    try:
        req_body = {
                'grant_type': 'refresh_token',
                'refresh_token': flask_session['refresh_token'],
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET
            }

        response = requests.post(TOKEN_URL, data = req_body)
        new_token_info = response.json()

        flask_session['access_token'] = new_token_info["access_token"]
        flask_session["expires_at"] = new_token_info["expires_in"] + datetime.datetime.now().timestamp()

    except:
        flash('There seems to be an error, please try logging in again', 'error')
        return redirect("/login")

# Launching the Flask app
if __name__ == "__main__":
    app.run(host = "0.0.0.0", port = int(os.environ.get("PORT", 5000)), debug = False)