from decimal import Decimal

from .models import Guild, transaction_model
from .services import get_balance, credit_tx, debit_tx

from peewee import DoesNotExist

class GuildObject:
    def __init__(self, server_id):
        """
        Initialize a Guild object with server_id and retrieve token_name and token_decimals.
        """
        self.server_id = server_id
        self.token_name, self.token_decimals, self.token_collector = self.retrieve_data()
    
    def retrieve_data(self):
        """
        Retrieve token_name and token_decimals from Guild based on server_id.
        """
        try:
            guild = Guild.get(Guild.server_id == int(self.server_id))
            return guild.token_name, guild.token_decimals, guild.collector_user_id
        except DoesNotExist:
            print(f"No Guild with server_id {self.server_id} found")
            return None, None
    
    def get_transactions(self, discord_user_id: int, max: int):
        """
        Retrieve the last 'max' number of successful transactions for a given discord_user_id.
        """
        model = transaction_model(server_id=self.server_id)
        return model.select().where(model.discord_user_id == discord_user_id, model.status == 'success').order_by(model.id.desc()).limit(max)

    def balance(self, discord_user_id: int) -> int:
        """
        Retrieve the balance for a given discord_user_id.
        """
        return get_balance(
                server_id=self.server_id, 
                discord_user_id=discord_user_id
            )

    def credit(self, discord_user_id: int, amount: float, note: str):
        """
        Credit a specific amount to a discord_user_id with a note.
        : expects the amount in eth as a float
        """
        converted_amount = self.from_eth(amount)

        return credit_tx(
            server_id=self.server_id, 
            discord_user_id=discord_user_id, 
            amount=converted_amount,
            note=note
        )

    def debit(self, discord_user_id: int, amount: str, note: str):
        """
        Debit a specific amount from a discord_user_id with a note.
        : expects the amount in wei as a string
        """

        # converted_amount = self.from_eth(amount)

        return debit_tx(
                self.server_id, 
                discord_user_id=discord_user_id, 
                amount=amount, 
                note=note
            )


    def to_eth(self, wei: str) -> Decimal:
        return Decimal(wei) / Decimal(10 ** self.token_decimals)

    def from_eth(self, eth: float) -> str:
        return str(int(Decimal(eth) * Decimal(10 ** self.token_decimals)))
    
    def to_locale(self, wei: str) -> str:
        return f"{self.to_eth(wei):n}" + " " + self.token_name
    
