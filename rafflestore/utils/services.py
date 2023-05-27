import datetime

from peewee import IntegrityError, DoesNotExist, fn

from utils.exceptions import InsufficientFunds

from utils.models import transaction_model, Raffle, Receipt, database

def create_raffle(
        server_id: int,
        title: str, 
        description: str, 
        image_url: str, 
        price: float, 
        duration: str,
        stock: int,
        max_qty_user=int,
        unique_winners=bool
        ):

    duration = duration.split(" ")

    if duration[-1].lower() == "h":
        duration = datetime.datetime.now() + datetime.timedelta(days=0, hours=int(duration[0]))
    elif duration[-1].lower() == "d":
        duration = datetime.datetime.now() + datetime.timedelta(days=int(duration[0]), hours=0)

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
                has_winner=False
            )
    except IntegrityError as e:
        print(e)
        raise IntegrityError



def get_balance(server_id: int, discord_user_id: int) -> str:
    """Return the latest balance of a user or 0"""
    try:
        transaction = transaction_model(server_id=server_id)
        query = transaction.select(fn.MAX(transaction.id)).where(transaction.discord_user_id == discord_user_id, transaction.status == "success").scalar()
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
                discord_user_id = discord_user_id,
                date = datetime.datetime.now(),
                previous_balance = balance,
                new_balance = new_balance,
                debit = "0",
                credit = amount,
                note = note,
                status = "success"
            )
        return new_balance
    except IntegrityError as e:
        return e


def debit_tx(server_id: int, discord_user_id: int, amount: str, note: str):
    """
    Record one debit transaction in the database
    """

    transaction = transaction_model(server_id = server_id)

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
                    date = datetime.datetime.now(),
                    previous_balance = balance,
                    new_balance = new_balance,
                    debit = amount,
                    credit = "0",
                    note = note,
                    status = "success"
                )
            return balance
        except IntegrityError as e:
            return e


""" Increment a existing raffle receipt or create a new one """
def increment_or_create_receipt(
        discord_user_id: str, 
        raffle: object, 
        quantity: int):
    
    # Calling database
    try:
        # Try get a receipt
        receipt = (Receipt
        .select()
        .where(
            Receipt.discord_user_id == discord_user_id, 
            Receipt.raffle == raffle.id)
        .get())
        # TODO Test below
        if receipt:
            # Update owned and execute
            update_receipts_owned = (Receipt
            .update(owned=Receipt.owned + quantity)
            .where(Receipt.id == receipt.id))
            update_receipts_owned.execute()
    except:
        Receipt.create(
            discord_user_id=discord_user_id, 
            raffle=raffle, 
            purchase_date=datetime.datetime.now(),
            owned = quantity
        )


def get_receipt(discord_user_id, raffle: Raffle):
    try:
        receipt = (Receipt
                   .select()
                   .where(
                       Receipt.discord_user_id == discord_user_id,
                       Receipt.raffle == raffle.id
                   )
                   .get())
        return receipt
    except Receipt.DoesNotExist:
        return None

    
def decrement_stock(raffle: object, quantity: int):
    query = (Raffle
    .update(sold=Raffle.sold + quantity, stock=Raffle.stock - quantity)
    .where(Raffle.id == raffle.id))
    query.execute()


def get_latest_transaction(server_id: int, discord_user_id: int):
    """Return the latest transaction"""
    transaction = transaction_model(server_id=server_id)
    try:
        return transaction.select().where(transaction.discord_user_id == discord_user_id).order_by(transaction.date.desc()).get()
    except DoesNotExist:
        return None


def get_transactions(server_id: int, discord_user_id: int, max: int):
    transaction = transaction_model(server_id=server_id)
    try:
        return transaction.select().where(transaction.discord_user_id == discord_user_id, transaction.status == 'success')[-max:]
    except DoesNotExist:
        return None