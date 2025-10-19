import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("MONGODB_URI")
name = os.getenv("MONGO_DB_NAME")

try:
    client = MongoClient(url)
    db = client[name]
    print("✅ MongoDB bilan bog‘landi!")
    print("Mavjud ma’lumotlar bazalari:", client.list_database_names())
except Exception as e:
    print("❌ Xato:", e)
