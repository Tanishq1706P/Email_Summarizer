import os
from pymongo import MongoClient
uri = os.environ['MONGO_URI']
client = MongoClient(uri)
db = client['email_summarizer']
print(f"Ping: {db.command('ping')}")
print(f"Emails: {db.emails.count_documents({})}")
print("Test insert:", db.test.insert_one({"test": "ok"}).acknowledged)