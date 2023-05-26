from peewee import *

from utils.database import db as database

class BaseModel(Model):
    class Meta:
        database = database

class Raffle(BaseModel):
    server_id = CharField()
    title = CharField()
    description = CharField()
    image_url = CharField()
    price = CharField()
    duration = DateTimeField()
    winners = SmallIntegerField()
    sold = IntegerField()
    visible = BooleanField()
    has_winner = BooleanField()



class Receipt(BaseModel):
    discord_user_id = CharField()
    raffle = ForeignKeyField(Raffle, backref="raffle_receipts")
    purchase_date = DateTimeField()
    owned = IntegerField()


def transaction_model(server_id: int):
    class Transaction(BaseModel):
        discord_user_id = CharField()
        date = DateTimeField()
        previous_balance = CharField()
        new_balance = CharField()
        debit = CharField()
        credit = CharField()
        status = CharField()
        note = CharField()

        class Meta:
            db_table = f"token_transaction_" + str(server_id)
    
    return Transaction


class Guild(BaseModel):
    # Server
    server_id = CharField(primary_key=True)
    server_name = CharField()
    role_admin = CharField()
    user_access_role = CharField()
    mod_role_id = CharField()
    collector_user_id = CharField()

    # Blockchain
    token_name = CharField()
    token_decimals = SmallIntegerField()

    # Channels
    support_channel_id = CharField()
    notification_channel_id = CharField()

    # Raffle
    raffle_message_id = CharField()
    raffle_channel_id = CharField()
    raffle_winner_channel_id = CharField()
