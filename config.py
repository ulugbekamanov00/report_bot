import os
from  dotenv import load_dotenv
load_dotenv()


TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = os.getenv("DB_NAME")
if not TOKEN or not DB_NAME:
    raise ValueError("BOT_TOKEN or DB_NAME not found in .env file")