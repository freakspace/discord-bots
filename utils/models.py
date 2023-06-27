from peewee import *

from utils.database import db as database

class BaseModel(Model):
    class Meta:
        database = database


class Player(BaseModel):
    discord_user_id = CharField(unique=True)
    join_date = DateTimeField()
    bank_pin = CharField(null=True)


class Raffle(BaseModel):
    server_id = CharField()
    title = CharField()
    description = CharField()
    image_url = CharField()
    price = CharField()
    duration = DateTimeField()
    stock = IntegerField(default=99999)
    max_qty_user = IntegerField(default=1) # Determine max qty a user can buy
    unique_winners = BooleanField() # Dertermine if the same winner can be picked more than once
    sold = IntegerField()
    visible = BooleanField()

    def has_winner(self):
        return Receipt.select().where((Receipt.raffle == self) & (Receipt.is_winner == True)).exists()


class Receipt(BaseModel):
    discord_user_id = CharField()
    raffle = ForeignKeyField(Raffle, backref="raffle_receipts")
    purchase_date = DateTimeField()
    owned = IntegerField()
    is_winner = BooleanField(default=False)


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
