import datetime
import json

from peewee import IntegrityError, DoesNotExist, fn

from utils.exceptions import InsufficientFunds

from utils.models import (
    transaction_model,
    Raffle,
    Receipt,
    database,
    Player,
    Guild,
    Lottery,
    LotteryNumber,
)


def create_raffle(
    server_id: int,
    title: str,
    description: str,
    image_url: str,
    price: float,
    duration: str,
    stock: int,
    max_qty_user=int,
    unique_winners=bool,
):
    duration = duration.split(" ")

    if duration[-1].lower() == "h":
        duration = datetime.datetime.now() + datetime.timedelta(
            days=0, hours=int(duration[0])
        )
    elif duration[-1].lower() == "d":
        duration = datetime.datetime.now() + datetime.timedelta(
            days=int(duration[0]), hours=0
        )

    try:
        with database.atomic():
            Raffle.create(
                server_id=server_id,
                title=title,
                description=description,
                image_url=image_url,
                price=price,
                duration=duration,
                stock=stock,
                max_qty_user=max_qty_user,
                unique_winners=unique_winners,
                sold=0,
                visible=True,
                has_winner=False,
            )
    except IntegrityError as e:
        print(e)
        raise IntegrityError


def get_balance(server_id: int, discord_user_id: int) -> str:
    """Return the latest balance of a user or 0"""
    try:
        transaction = transaction_model(server_id=server_id)
        query = (
            transaction.select(fn.MAX(transaction.id))
            .where(
                transaction.discord_user_id == discord_user_id,
                transaction.status == "success",
            )
            .scalar()
        )
        balance = transaction.get(id=query).new_balance
    except DoesNotExist:
        balance = "0"

    return balance


def credit_tx(server_id: int, discord_user_id: int, amount: str, note: str):
    """
    Record one credit transaction in the database
    """

    transaction = transaction_model(server_id=server_id)

    balance = get_balance(server_id=server_id, discord_user_id=discord_user_id)

    new_balance = str(int(balance) + int(amount))
    print(f"Crediting {amount}")
    try:
        with database.atomic():
            transaction.create(
                discord_user_id=discord_user_id,
                date=datetime.datetime.now(),
                previous_balance=balance,
                new_balance=new_balance,
                debit="0",
                credit=amount,
                note=note,
                status="success",
            )
        return new_balance
    except IntegrityError as e:
        return e


def debit_tx(server_id: int, discord_user_id: int, amount: str, note: str):
    """
    Record one debit transaction in the database
    """

    transaction = transaction_model(server_id=server_id)

    balance = get_balance(server_id=server_id, discord_user_id=discord_user_id)

    if int(balance) < int(amount):
        raise InsufficientFunds("Not enough funds")
    else:
        new_balance = str(int(balance) - int(amount))
        print(f"Debiting {amount}")
        try:
            with database.atomic():
                transaction.create(
                    discord_user_id=discord_user_id,
                    date=datetime.datetime.now(),
                    previous_balance=balance,
                    new_balance=new_balance,
                    debit=amount,
                    credit="0",
                    note=note,
                    status="success",
                )
            return balance
        except IntegrityError as e:
            return e


""" Increment a existing raffle receipt or create a new one """


def increment_or_create_receipt(discord_user_id: str, raffle: object, quantity: int):
    # Calling database
    try:
        # Try get a receipt
        receipt = (
            Receipt.select()
            .where(
                Receipt.discord_user_id == discord_user_id, Receipt.raffle == raffle.id
            )
            .get()
        )
        # TODO Test below
        if receipt:
            # Update owned and execute
            update_receipts_owned = Receipt.update(
                owned=Receipt.owned + quantity
            ).where(Receipt.id == receipt.id)
            update_receipts_owned.execute()
    except:
        Receipt.create(
            discord_user_id=discord_user_id,
            raffle=raffle,
            purchase_date=datetime.datetime.now(),
            owned=quantity,
        )


def get_receipt(discord_user_id, raffle: Raffle):
    try:
        receipt = (
            Receipt.select()
            .where(
                Receipt.discord_user_id == discord_user_id, Receipt.raffle == raffle.id
            )
            .get()
        )
        return receipt
    except Receipt.DoesNotExist:
        return None


def decrement_stock(raffle: object, quantity: int):
    query = Raffle.update(
        sold=Raffle.sold + quantity, stock=Raffle.stock - quantity
    ).where(Raffle.id == raffle.id)
    query.execute()


def get_latest_transaction(server_id: int, discord_user_id: int):
    """Return the latest transaction"""
    transaction = transaction_model(server_id=server_id)
    try:
        return (
            transaction.select()
            .where(transaction.discord_user_id == discord_user_id)
            .order_by(transaction.date.desc())
            .get()
        )
    except DoesNotExist:
        return None


def get_transaction(server_id: int, tx_id: int):
    try:
        transaction_model = transaction_model(server_id=server_id)
        return transaction_model.get(id=tx_id)
    except:
        return None


def get_transactions(server_id: int, discord_user_id: int, max: int):
    transaction_model = transaction_model(server_id=server_id)
    try:
        return transaction_model.select().where(
            transaction_model.discord_user_id == discord_user_id,
            transaction_model.status == "success",
        )[-max:]
    except DoesNotExist:
        return None


def get_or_create_player(discord_user_id: int):
    try:
        player = Player.get(Player.discord_user_id == str(discord_user_id))
        return player
    except:
        try:
            with database.atomic():
                player = Player.create(
                    discord_user_id=discord_user_id, join_date=datetime.datetime.now()
                )
            return player
        except IntegrityError as e:
            print(f"Integrety error: {e}")
            return None


def create_transaction_table(server_id: int):
    """Creates a new guild transaction table in the database"""
    tables = database.get_tables()

    table_name = f"token_transaction_" + str(server_id)

    if table_name not in tables:
        print("Creating Table")
        model = transaction_model(server_id=server_id)

        with database:
            database.create_tables([model])


def create_guild(server_id: int, server_name: str, role_admin: int):
    try:
        Guild.get(Guild.server_id == server_id)
    except DoesNotExist:
        try:
            with database.atomic():
                Guild.create(
                    server_id=server_id, server_name=server_name, role_admin=role_admin
                )
        except IntegrityError as e:
            return e


def create_lottery_ticket(discord_user_id: int, lottery_id: int, numbers: list):
    try:
        with database.atomic():
            lottery_ticket = LotteryNumber.create(
                discord_user_id=discord_user_id,
                lottery_id=lottery_id,
                purchase_time=datetime.datetime.now(),
                numbers=json.dumps(numbers),
            )
            return lottery_ticket
    except IntegrityError as e:
        print(e)
        return


def start_new_lottery(
    server_id: int, end_time: str, price: str, price_pool: str, jackpot_bonus: str
):
    end_time = datetime.datetime.now() + datetime.timedelta(days=int(end_time), hours=0)

    try:
        with database.atomic():
            lottery = Lottery.create(
                server_id=server_id,
                end_time=end_time,
                price=price,
                prize_pool=price_pool,
                sold=0,
                jackpot_bonus=jackpot_bonus,
            )
            return lottery
    except IntegrityError as e:
        print(e)
        return None


def increment_lottery_total_sold(lottery_id: int, amount: int):
    # Update total count on raffle
    prize_pool = Lottery.get(id=lottery_id).prize_pool

    if prize_pool:
        prize_pool = int(prize_pool)
    else:
        prize_pool = 0

    query = Lottery.update(
        sold=Lottery.sold + 1, prize_pool=round(prize_pool + amount)
    ).where(Lottery.id == lottery_id)

    query.execute()
