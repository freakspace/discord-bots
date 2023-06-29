from utils.database import db as database

from utils.models import (
    Raffle,
    Receipt,
    transaction_model,
    Guild,
    Player,
    Lottery,
    LotteryNumber,
)

transaction_table = transaction_model(1020233562454249502)


def create_tables():
    database.connect()
    database.create_tables(
        [Raffle, Receipt, Guild, transaction_table, Player, Lottery, LotteryNumber]
    )
    database.close()


create_tables()
