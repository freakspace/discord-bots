import os

from dotenv import load_dotenv

from peewee import MySQLDatabase, SqliteDatabase

load_dotenv()

environment = os.getenv("ENVIRONMENT")

db = None

if environment == "local":

    use_sqlite = os.getenv("USE_SQLITE")

    if use_sqlite == "true":
        db = SqliteDatabase('lifty.db')
    else:
    # Connect to a MySQL database on network.
        db = MySQLDatabase(
            database=os.getenv("DATABASE_LOCAL"), 
            user=os.getenv("USER_LOCAL"), 
            password=os.getenv("PASSWORD_LOCAL"),
            host=os.getenv("HOST_LOCAL"), 
            port=int(os.getenv("PORT_LOCAL"))
        )

if environment == "stage-devnet":
    # Connect to a MySQL database on network.
    db = MySQLDatabase(
        database=os.getenv("DATABASE_STAGE_DEVNET"), 
        user=os.getenv("USER_STAGE_DEVNET"), 
        password=os.getenv("PASSWORD_STAGE_DEVNET"),
        host=os.getenv("HOST_STAGE_DEVNET"), 
        port=int(os.getenv("PORT_STAGE_DEVNET"))
    )

if environment == "stage-mainnet":
    # Connect to a MySQL database on network.
    db = MySQLDatabase(
        database=os.getenv("DATABASE_STAGE_MAINNET"), 
        user=os.getenv("USER_STAGE_MAINNET"), 
        password=os.getenv("PASSWORD_STAGE_MAINNET"),
        host=os.getenv("HOST_STAGE_MAINNET"), 
        port=int(os.getenv("PORT_STAGE_MAINNET"))
    )

if environment == "prod":
    # Connect to a MySQL database on network.
    db = MySQLDatabase(
        database=os.getenv("DATABASE_PROD"), 
        user=os.getenv("USER_PROD"), 
        password=os.getenv("PASSWORD_PROD"),
        host=os.getenv("HOST_PROD"), 
        port=int(os.getenv("PORT_PROD"))
    )
