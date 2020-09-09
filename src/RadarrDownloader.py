#!/usr/bin/python
import os
import urllib
import json
import requests
import time
import sys
import json
from datetime import datetime,timedelta

import functools
print = functools.partial(print, flush=True)


class color:
   PURPLE = '\033[1;35;48m'
   CYAN = '\033[1;36;48m'
   BOLD = '\033[1;37;48m'
   BLUE = '\033[1;34;48m'
   GREEN = '\033[1;32;48m'
   YELLOW = '\033[1;33;48m'
   RED = '\033[1;31;48m'
   BLACK = '\033[1;30;48m'
   UNDERLINE = '\033[4;37;48m'
   END = '\033[1;37;0m'

# Radarr API Key, get it in Settings->General->Security of Sonarr pages
try:
    apiKey = os.environ["APIKEY"]
# Radarr Host Name: Add reverse proxy or direct IP:port, no trailing slash
    hostName = os.environ["HOST"]
except KeyError:
    print("Please set HOST and APIKEY variables")
    quit()


search_delay = int(os.environ.get("SEARCH_DELAY", "900"))
history_delay = int(os.environ.get("HISTORY_DELAY","90"))
refresh_delay = int(os.environ.get("REFRESH_DELAY","60"))
failure_delay = int(os.environ.get("FAILURE_DELAY","300"))
skip_path_contains = os.environ.get("SKIP_PATH","")

def getData(radarrHost):
    response = requests.get(radarrHost)
    json = response.json()
    return json

def postData(radarrHost, data):
    json_data = json.dumps(data)
    x = requests.post(radarrHost, json_data)
    return x.text

def getAllMovies():
    print ("=== Getting a list of all movies from radarr, this can take a couple of minutes ===")

    allMoviesJSON = getData(hostName + "/api/v3/movie?apikey=" + apiKey)
    print (f"-- Got a list of {str(len(allMoviesJSON))} movies")

    return allMoviesJSON

def getSearchKey():
    try:
        searchKey = open("/config/MoviesSearch-Key.txt")
        lines = searchKey.read().split('\n')
    except Exception:
        lines = []
    return lines

def addToGrabbedFile(movie):
    grabbedFile = open("/config/MoviesSearch-Grabbed.txt","a+")
    grabbedFile2 = open("/config/MoviesSearch-Grabbed.txt","r")

    text = grabbedFile2.read().split('\n')
    grabbedFile2.close
    if not str(movie['id']) in text:
        grabbedFile.write(str(movie['id'])+"\n")
    grabbedFile.close

def addToUpgradedFile(movie):
    upgradeFile = open("/config/MoviesSearch-Upgraded.txt","a+")
    upgradeFile2 = open("/config/MoviesSearch-Upgraded.txt","r")
    text = upgradeFile2.read().split('\n')
    upgradeFile2.close
    upgradestring = str(movie['id'])+ " - " + movie['title'] + " (" + str(movie['year']) + ")"
    found = False
    for line in text:
        if line.startswith(str(movie['id']) + " -"):
            found = True
    if found == False:
        upgradeFile.write(upgradestring+"\n")
    upgradeFile.close 

def getCodec(movie):
    try:
        codec = movie['movieFile']['mediaInfo']['videoCodec']
        print(f"-- ID {movie['id']}: Movie file is using '{codec}' codec")

    except Exception:
        codec = ""
        movie = refreshMovie(movie)

        try:
            codec = movie['movieFile']['mediaInfo']['videoCodec']
            print(f"-- ID {movie['id']}: Movie file is using '{codec}' codec")

        except Exception:
            codec = ""


    return codec

def refreshMovie(movie):
    print (f"-- ID {movie['id']}: Exception received reading codec for {movie['title']} ({movie['year']}) triggering RefreshMovie.")
    params = {'name':"RefreshMovie", 'movieIds':[movie['id']]}
    postData(hostName + "/api/v3/command?apikey=" + apiKey, params)
    time.sleep(refresh_delay)
    movie2 = getSingleMovie(movie['id'])
    return movie2


def searchMovie(movie):

    if str(movieID) in searchkey:
        print (f"-- ID {movieID}: Already searched {movie['title']} ({movie['year']}), SKIPPED...")
        return False
    checkHealth()
    params = {'name':"MoviesSearch",'movieIds':[movie['id']]}
    postData(hostName + "/api/v3/command?apikey=" + apiKey, params)
    searchKey = open("/config/MoviesSearch-Key.txt","a+")
    searchKey.write(str(movie['id'])+"\n")
    searchKey.close
    return True

def checkHealth():   

    healthy = False # initialize before use
    while not healthy:

        healthy = True # assume healthy
        health = getData(hostName + "/api/v3/health?apikey=" + apiKey)
        
        if not health == "[]":            
            for item in health:
                message = item['message']
                if message.__contains__("All search-capable indexers are"):
                    healthy = False                    
                    break
                if message.__contains__("All download clients are unavailable"):
                    healthy = False                    
                    break
                if message.__contains__("Unable to communicate with"):
                    healthy = False
                    break                

        if not healthy:
            print (f"{color.YELLOW}-- WARNING: {message}. Sleeping for {failure_delay} seconds.{color.END}")
            time.sleep(failure_delay)

def getSingleMovie(id):
    movie = getData(hostName + "/api/v3/movie/" + str(id) + "?apikey=" + apiKey)
    return movie

def checkHistory(movie):
    print(f"-- ID {movie['id']}: Checking Radarr History (100 rows)")

    history = getData(hostName + "/api/v3/history?apikey=" + apiKey +"&pageSize=100")
    foundHistory = False
    #print(history)
    for hist_item in history['records']:
        if hist_item['eventType'] != "grabbed":
            continue
        if hist_item['movieId'] == movie['id']:
            print(f"-- ID {movie['id']}: Found 'grabbed' event in recent history {hist_item['sourceTitle']}")
            addToGrabbedFile(movie)
            foundHistory = True
            break
    if foundHistory == True:
        timestr = (datetime.now() + timedelta(seconds=search_delay)).strftime('%H:%M:%S')
        print(f"-- ID {movie['id']}: Waiting for {str(search_delay)} seconds... (until {timestr})")
        time.sleep(search_delay)
        movie = getSingleMovie(movie['id'])
        codec = getCodec(movie)
        if codec.startswith('x265'):
            print(f"-- ID {movie['id']}: 'grabbed' {movie['title']} ({movie['year']}) is x265 already. {color.GREEN}SWEET!{color.END}")
            addToUpgradedFile(movie)

    else:
        print(f"-- ID {movie['id']}: Movie Searched but not found in history. Assume no upgrade available. Moving on.")
    return

def shouldSkipMovie(movie):
    if not movie['hasFile']:
        print(f"-- ID {movie['id']}: Movie not downloaded, SKIPPED.")
        return True

    if skip_path_contains:        
        paths = skip_path_contains.split(',')
        for path in paths:            
            if movie['path'].__contains__(path):
                print(f"-- ID {movie['id']}: Path contains skipped string '{path}' , SKIPPED.")
                return True

    return False

searchkey = getSearchKey()
#print (searchkey)
allMoviesJSON = getAllMovies()

# for each movie
for movie in allMoviesJSON:
    movieID = movie['id']
    print (f"\n{color.RED}=== ID {movieID}: {movie['title']} ({movie['year']}) ==={color.END}")

    if shouldSkipMovie(movie):
        continue

    codec = getCodec(movie)

    if not codec.startswith('x265'):
        print (f"-- ID {movieID}: NOT x265, triggering MoviesSearch API.")
        if searchMovie(movie) == True:
            print (f"-- ID {movieID}: Success. Waiting for {str(history_delay)} seconds before checking Radarr history.")
            time.sleep(history_delay)
            checkHistory(movie)
    else:
        if (str(movieID)) in searchkey:
            print(f"-- ID {movieID}: {movie['title']} ({movie['year']}) has been searched before, and it's now x265. {color.GREEN}AWESOME!{color.END}")
            addToUpgradedFile(movie)
        else:
            print(f"-- ID {movieID}: movie is already x265. Moving on.")


