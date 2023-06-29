import json
from datetime import datetime

from peewee import *
from playhouse.mysql_ext import JSONField

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
    max_qty_user = IntegerField(default=1)  # Determine max qty a user can buy
    unique_winners = (
        BooleanField()
    )  # Dertermine if the same winner can be picked more than once
    sold = IntegerField()
    visible = BooleanField()

    def has_winner(self):
        return (
            Receipt.select()
            .where((Receipt.raffle == self) & (Receipt.is_winner == True))
            .exists()
        )


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


class Lottery(BaseModel):
    server_id = CharField()
    end_time = DateTimeField()
    price = CharField()
    prize_pool = CharField()
    sold = IntegerField()
    numbers_picked = JSONField(null=True)
    prize_table = JSONField(null=True)
    jackpot_bonus = CharField()

    def get_numbers(self):
        if self.numbers_picked != None:
            return json.loads(self.numbers_picked)
        else:
            raise Exception("Numbers has not been picked")

    def is_salabe(self):
        return self.end_time < datetime.datetime.now()


class LotteryNumber(BaseModel):
    discord_user_id = CharField()
    lottery_id = CharField()
    purchase_time = DateTimeField()
    numbers = JSONField()
    numbers_correct = SmallIntegerField(null=True)
    prize = CharField(null=True)
    prize_claimed = BooleanField(default=False)

    class Meta:
        db_table = "lottery_number"

    def get_numbers(self):
        return json.loads(self.numbers)

    def get_claimed(self):
        if self.prize == "0":
            return "❌"
        if self.prize_claimed:
            return "✅"
        else:
            return "🔳"

    def get_prize(self):
        if self.prize != None:
            return self.prize
        else:
            return None
