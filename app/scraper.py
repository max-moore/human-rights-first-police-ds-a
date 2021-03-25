"""
Pulls tweets from twitter based on a keyword search of popular
tweets. These tweets are filtered using the TextMatcher class in textmatcher.py. 
If these tweets are determined by the model to report police use of force 
they will be input into the a database.
"""

import dataset
import json
import tweepy
from sqlalchemy.exc import ProgrammingError
from os import getenv
from dotenv import load_dotenv
import psycopg2
import geopy

from app.textmatcher import TextMatcher
from app.training_data import ranked_reports
from app.helper_funcs import tweet_dupes
from geopy import geocoders
from geopy.geocoders import Nominatim
#import BD url from .env file
load_dotenv()
#make database connection
db = dataset.connect(getenv("DB_URL"))

#instantiate TextMatcher class to make category predictions on tweets
model = TextMatcher(ranked_reports)

#import twitter api credential from .env file
CONSUMER_KEY = getenv("CONSUMER_KEY")
CONSUMER_SECRET = getenv("CONSUMER_SECRET")
ACCESS_KEY = getenv("ACCESS_KEY")
ACCESS_SECRET = getenv("ACCESS_SECRET")

# make twitter API connection and instatiate connection class using tweepy
auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)
api = tweepy.API(auth)

# create geopy object
geolocator = Nominatim(user_agent="incident_location_lookup")

#quick DB query statment to run in the function
statement = 'SELECT id_str FROM twitter_potential_incidents ORDER BY id_str DESC LIMIT 1'
#words to ensure are included in the tweet, THIS LIST SHOULD BE EXPANDED.
filter_words = ["police", "officer", "cop"]
#make sure when then tweet runs through the model the tweet recieves one fo the following ranks,
# If model produces a Rank 0, it will not be included in the DB
ranked_reports = ["Rank 1 - Police Presence", "Rank 2 - Empty-hand", "Rank 3 - Blunt Force", 
                "Rank 4 - Chemical & Electric", "Rank 5 - Lethal Force"]

def update_twitter_data(reddit_db):
    """
    Function does not take any variables, functions only purpose to be called when needed.
    This function will pull tweets from twitter that a report police use of force, filter using
    the textmatcher class, and populate the database.
    """
    # quick database query to see what the id of the last imported tweet was.
    conn = psycopg2.connect(getenv("DB_URL"))
    curs = conn.cursor()
    curs.execute(statement)
    conn.commit()
    #maxid = curs.fetchall()[0][0]
    curs.close()
    conn.close()

    # loop through through the imported tweets.
    # SINCE_ID=maxid ONCE TABLE IS CREATED
    for status in tweepy.Cursor(api.search, q="police", lang='en', result_type='popular', since_id=0).items():
        #This assigns a category to the tweet
        category = model(status.text)
        # filters out retweets, tweets that don't include the filter words, and Rank 0 categories
        # tweet_dupes function checks to see if tweet already exists in reddit posts
        conditions = (not 'RT @' in status.text) and \
                    any(word in status.text for word in filter_words) \
                    and (category in ranked_reports) \
                    and tweet_dupes(status, reddit_db)
        # imports tweets into the DB
        if conditions:
            description = status.user.description
            loc = status.user.location
            text = status.text
            coords = status.coordinates
            geo = status.geo
            name = status.user.screen_name
            user_created = status.user.created_at
            id_str = status.id_str
            created = status.created_at
            source = status.user.url
            language = status.lang
            
            #generating geodata
            g = geocoders.GoogleV3(api_key='AIzaSyCE5lVARWiC2QVx4gbXnomR5_rydM3vndQ')
            
            try:
                glocation = g.geocode(loc, timeout=10)
                city = glocation.address,
                state = glocation.address,
                lat = glocation.latitude,
                long = glocation.longitude
            except AttributeError:
                print("Problem with data or cannot Geocode.")
             
            title=text.split()[:8]

            if geo is not None:
                geo = json.dumps(geo)

            if coords is not None:
                coords = json.dumps(coords)

            table = db["twitter_potential_incidents"]
            try:
                table.insert(dict(
                    user_description=description,
                    user_location=loc,
                    coordinates=coords,
                    text=text,
                    geo=geo,
                    # inserting geodata into table
                    city=city,
                    state=state,
                    lat=lat,
                    long=long,
                    title=title,
                    #
                    user_name=name,
                    user_created=user_created,
                    id_str=id_str,
                    created=created,
                    source = source,
                    language = language,
                    category = category
                    ))
            except ProgrammingError as err:
                print(err)

    def on_error(self, status_code):
        if status_code == 420:
            #return False if tweepy connection fails
            return False

    