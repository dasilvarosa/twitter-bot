import os
import json
import time
import random
from pathlib import Path

import tweepy
import requests

# ---------- Config from environment ----------
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

NUM_TWEETS_TO_CHECK  = int(os.getenv("NUM_TWEETS", "20"))     # how many of your newest tweets to scan
FOLLOW_CAP_PER_RUN   = int(os.getenv("FOLLOW_CAP", "15"))     # max follows per script run
PAGE_LIMIT_PER_TWEET = int(os.getenv("PAGE_LIMIT", "1"))      # liker pages per tweet (100 per page)
SLEEP_MIN            = float(os.getenv("SLEEP_MIN", "2"))     # seconds between follows (min)
SLEEP_MAX            = float(os.getenv("SLEEP_MAX", "4"))     # seconds between follows (max)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")                  # required to notify
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")              # required to notify

STATE_FILE = Path("processed_likers.json")

# ---------- Basic validation ----------
missing = [k for k,v in {
    "API_KEY":API_KEY, "API_SECRET":API_SECRET,
    "ACCESS_TOKEN":ACCESS_TOKEN, "ACCESS_TOKEN_SECRET":ACCESS_TOKEN_SECRET,
    "TELEGRAM_TOKEN":TELEGRAM_TOKEN, "TELEGRAM_CHAT_ID":TELEGRAM_CHAT_ID
}.items() if not v]
if missing:
    raise SystemExit(f"Missing env vars: {', '.join(missing)}")

# ---------- Init Twitter clients ----------
# OAuth1 for user-context write (follow)
auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

# Tweepy v2 client (reads + writes with user context)
client_v2 = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True
)

# ---------- Load state ----------
if STATE_FILE.exists():
    try:
        processed = set(json.loads(STATE_FILE.read_text()))
    except Exception:
        processed = set()
else:
    processed = set()

def save_state():
    try:
        STATE_FILE.write_text(json.dumps(list(processed)))
    except Exception as e:
        print(f"[WARN] Could not save state: {e}")

# ---------- Helpers ----------
def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        r = requests.post(url, data=payload, timeout=15)
        ok = r.status_code == 200
        print(f"[TELEGRAM] {r.status_code}: {r.text[:200]}")
        return ok
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

def get_my_user_id():
    me = client_v2.get_me()
    if not me or not me.data:
        raise RuntimeError("Could not resolve own user ID; check Twitter keys/permissions.")
    return str(me.data.id)

def get_latest_tweet_ids(user_id: str, limit: int):
    ids = []
    resp = client_v2.get_users_tweets(
        id=user_id,
        max_results=min(100, max(5, limit)),
        exclude=["replies", "retweets"],
        tweet_fields=["id"]
    )
    if resp and resp.data:
        for t in resp.data[:limit]:
            ids.append(str(t.id))
    return ids

def get_likers_for_tweet(tweet_id: str, max_pages: int):
    users = []
    pagination_token = None
    pages = 0
    while pages < max_pages:
        resp = client_v2.get_liking_users(
            id=tweet_id,
            pagination_token=pagination_token,
            max_results=100,
            user_fields=["id","username","protected","verified"]
        )
        if resp and resp.data:
            users.extend(resp.data)
        meta = getattr(resp, "meta", {}) or {}
        pagination_token = meta.get("next_token")
        pages += 1
        if not pagination_token:
            break
    return users

def already_following(target_user_id: str):
    try:
        friendship = api_v1.get_friendship(source_id=my_id, target_id=target_user_id)
        if friendship and len(friendship) == 2:
            return friendship[0].following
    except Exception as e:
        print(f"[FOLLOW CHECK ERROR] {target_user_id}: {e}")
    return False

def follow_user(target_user_id: str):
    try:
        client_v2.follow(target_user_id=target_user_id)  # no-op if already following
        return True
    except tweepy.TweepyException as e:
        print(f"[FOLLOW ERROR] {target_user_id}: {e}")
        return False

# ---------- Main ----------
if __name__ == "__main__":
    try:
        my_id = get_my_user_id()
        print(f"[INFO] Running as user {my_id}")
    except Exception as e:
        print(f"[FATAL] {e}")
        send_telegram_message("Followed 0 new users (auth error)")
        raise SystemExit(1)

    tweet_ids = get_latest_tweet_ids(my_id, NUM_TWEETS_TO_CHECK)
    print(f"[INFO] Found {len(tweet_ids)} recent tweets to scan")

    follows_done = 0

    for tid in tweet_ids:
        if follows_done >= FOLLOW_CAP_PER_RUN:
            break

        likers = get_likers_for_tweet(tid, PAGE_LIMIT_PER_TWEET)
        print(f"[INFO] Tweet {tid}: {len(likers)} liker(s) fetched (capped by pages)")

        for u in likers:
            if follows_done >= FOLLOW_CAP_PER_RUN:
                break

            uid = str(u.id)
            if uid in processed or uid == my_id:
                continue

            if getattr(u, "protected", False):
                processed.add(uid)
                continue

            if already_following(uid):
                print(f"[SKIP] Already following @{getattr(u, 'username', uid)}")
                processed.add(uid)
                continue

            if follow_user(uid):
                follows_done += 1
                uname = getattr(u, "username", uid)
                print(f"[FOLLOWED] @{uname} ({uid})  total={follows_done}")
            else:
                print(f"[SKIP] Failed to follow {uid}")

            processed.add(uid)
            save_state()

            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    msg = f"Followed {follows_done} new users"
    print(f"[SUMMARY] {msg}")
    send_telegram_message(msg)
