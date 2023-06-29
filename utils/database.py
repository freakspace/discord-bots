import os
import logging

from dotenv import load_dotenv

from peewee import MySQLDatabase, SqliteDatabase

print("TESTER")
load_dotenv()

environment = os.getenv("ENVIRONMENT")
print(f"Environment is: {environment}")


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.info("Before db initialization")
db = SqliteDatabase("database.db")
logger.info(f"db is {db}")
