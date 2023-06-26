from http import server
import os
import hashlib

import discord
from discord.ext import commands, tasks
from discord.commands import OptionChoice

from peewee import DoesNotExist

from utils.utils import send_hall_message, get_domain
from utils.api_service import get_user_deposit_address
from utils.models import (
    Player,
    Thread,
    Guild,
    get_or_create_player,
    create_guild,
    create_transaction_table,
    get_total_flips,
    get_total_solana_balance,
    get_total_sold_tickets,
    get_transaction_fee
)
from utils.guild_object import GuildObject

from utils.utils import *

import settings

environment = os.getenv("ENVIRONMENT")

banking_bot = int(os.getenv("BANK_BOT_ID"))

guild_ids = [int(guild.server_id) for guild in Guild.select()]

# TODO Add a try again to the withdrawal fails
# TODO A global stats command
# TODO Bool choices should be global
# TODO Fix the sol balance to show 0 instead of the scientific number
# TODO Command: Flips for each token and sol, sold SOL raffle tickets, total deposits, earned SOL withdrawal fees


def hash_password(raw_password: str):
    message = raw_password.encode()
    return hashlib.sha256(message).hexdigest()


def check_password(raw_password: str, encrypted_password: str):
    message = raw_password.encode()
    pincode = hashlib.sha256(message).hexdigest()
    if pincode == encrypted_password:
        return True
    else:
        return False


async def open_account(interaction: discord.Interaction, token: object):
    player = get_or_create_player(discord_user_id=interaction.user.id)

    guild_access_role = get_access_role(server_id=interaction.guild.id)

    if guild_access_role:
        roles = interaction.user.roles
        access_role = interaction.guild.get_role(guild_access_role)
        if access_role not in roles:
            embed = discord.Embed(
                title="",
                description=f"You got to have the {access_role} role to do that...",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    if player.bank_pin:
        await interaction.response.send_modal(CheckPinModal(title="Enter Your Pincode", encrypted_password=player.bank_pin, token=token))
    else:
        view = discord.ui.View()
        view.add_item(item=CreatePinButton(token=token, player=player))

        embed = discord.Embed(
            title="",
            description="""
I see it’s your first time here…
You’ll need to **Create An Account** here at the bank.
Click the button below to set up your secure pin code first.

⚠️ Note: Make sure you **REMEMBER** the pin
                    """,
            color=discord.Color.yellow()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CheckPinModal(discord.ui.Modal):
    def __init__(self, token, encrypted_password, *args, **kwargs):
        self.encrypted_password = encrypted_password
        self.token = token
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Pincode",
                      placeholder="Enter Your Pincode To View Your Account"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pincode = self.children[0].value

        if check_password(pincode, self.encrypted_password):
            # Get user deposit address
            print("Getting deposit address...")
            deposit_address = get_user_deposit_address(
                server_id=interaction.guild.id, discord_user_id=interaction.user.id)
            print(deposit_address)
            # Prepare embed
            embed = discord.Embed(
                title=f"💳 {interaction.user.display_name}'s {self.token.value} Account",
                description=f"""
**__Your Discord Wallet Address__**: 
{deposit_address}
            """,
                color=discord.Color.green()
            )

            embed.add_field(name=f":moneybag: {self.token.value} Balance",
                            value=f"`{self.token.to_locale_from_lamports(self.token.balance(discord_user_id=interaction.user.id))}`")
            embed.set_thumbnail(url=interaction.user.display_avatar)

            # Get token
            if self.token.value == settings.solana_name:
                await interaction.followup.send(embed=embed, view=UserBankingViewSolana(), ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=UserBankingViewToken(), ephemeral=True)

        else:
            embed = discord.Embed(
                title=":x: Access Denied",
                description="You entered the wrong Pincode.",
                color=discord.Color.red()
            )

            view = discord.ui.View()
            view.add_item(item=ViewAccountButton(
                label="Try Again", token=self.token))
            view.add_item(item=ForgotPinButton())

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class CreatePinModal(discord.ui.Modal):
    def __init__(self, token: object, *args, **kwargs):
        self.token = token
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Create Pincode",
                      placeholder="Enter a Secure Pincode You Will Remember"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pincode = self.children[0].value

        hashed_pincode = hash_password(pincode)

        view = discord.ui.View()

        try:
            update_pincode = (Player
                              .update(bank_pin=hashed_pincode)
                              .where(Player.discord_user_id == interaction.user.id))
            update_pincode.execute()
        except:
            embed = discord.Embed(
                title=":octagonal_sign: Error",
                description="We couldm't set a pincode.Try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return

        embed = discord.Embed(
            title=":white_check_mark: Pincode Set & Account Created",
            description="""
Your **Pincode** was successfully set and your account was **created.**
Please make sure you **remember ** your pincode, you will need it to **view** your account.

View your account now by clicking the **button** below, and entering your **new pincode**.
                    """,
            color=discord.Color.green()
        )

        guild = Guild.get(Guild.server_id == interaction.guild_id)

        if guild.bank_thumbnail_image:
            url = guild.bank_thumbnail_image
        else:
            url = interaction.client.get_user(banking_bot).display_avatar

        embed.set_thumbnail(url=url)
        view.add_item(item=ViewAccountButton(
            label=f"View {self.token.value} Account", token=self.token))

        # Get or generate address
        get_user_deposit_address(
            server_id=interaction.guild.id, discord_user_id=interaction.user.id)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class WithdrawModal(discord.ui.Modal):
    def __init__(self, balance, token, *args, **kwargs):
        self.balance = balance
        self.token = token
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label=f"Balance: {self.token.to_locale_from_lamports(self.balance)})"[
                      0:45], placeholder=f"Enter Amount To Withdraw"))
        self.add_item(discord.ui.InputText(label=f"SOLANA Address",
                      placeholder=f"Enter Receipient Address"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            amount = float(self.children[0].value)
        except ValueError:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                            """,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        amount_in_lamports = self.token.to_lamports(amount=amount)

        balance = self.token.balance(discord_user_id=interaction.user.id)

        if amount_in_lamports <= 0:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                            """,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif amount_in_lamports > balance:
            embed = discord.Embed(
                title=":octagonal_sign: Balance too low",
                description=f"""
Withdrawal amount: {amount_in_lamports}
Balance: {balance}
                            """,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            fee = self.token.fee_total(amount_in_lamports=amount_in_lamports)
            amount_after_fee = amount_in_lamports - fee
            embed = discord.Embed(
                title=f"Confirm Withdrawal",
                description=f"""
I must remind you…
There is a **{self.token.fee():.2%} Banker Fee** to withdraw your {self.token.value}

:arrow_up: Withdrawal Amount: `{self.token.to_locale(amount)}`
:coin: You Receive After Fee: `{self.token.to_locale_from_lamports(amount_after_fee)}`

**__Recipient Wallet:__** {self.children[1].value}
                    """,
                color=discord.Color.red()
            )

            guild = Guild.get(Guild.server_id == interaction.guild_id)

            if guild.bank_thumbnail_image:
                url = guild.bank_thumbnail_image
            else:
                url = interaction.client.get_user(banking_bot).display_avatar

            embed.set_thumbnail(url=url)
            view = discord.ui.View()

            view.add_item(ConfirmWithdrawal(
                amount=amount_in_lamports,
                message_id=interaction.message.id,
                deposit_address=get_user_deposit_address(
                    server_id=interaction.guild.id, discord_user_id=interaction.user.id),
                token=self.token,
                withdrawal_address=self.children[1].value
            ))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ConfirmWithdrawal(discord.ui.Button):
    def __init__(
        self,
        amount: int,
        message_id: int,
        deposit_address: str,
        token: object,
        withdrawal_address: str
    ):
        self.amount = amount
        self.message_id = message_id
        self.deposit_address = deposit_address
        self.token = token
        self.withdrawal_address = withdrawal_address
        super().__init__(
            label="Confirm Withdrawal",
            style=discord.ButtonStyle.red,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        transaction = None
        tx_id = None

        # Check users balance
        balance = self.token.balance(discord_user_id=interaction.user.id)

        if self.amount > balance:
            embed = discord.Embed(
                title=":octagonal_sign: Balance too low",
                description=f"""
Withdrawal amount: {self.amount}
Balance: {self.token.to_locale_from_lamports(balance)}
                            """,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        else:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Confirming On-Chain",
                          emoji="⏳", style=discord.ButtonStyle.grey, disabled=True))
            await interaction.followup.edit_message(message_id=interaction.message.id, view=view)
            # Calculate fees
            if self.token.fee() > 0:
                fee = self.token.fee_total(amount_in_lamports=self.amount)
                amount_after_fee = self.amount - fee
            else:
                fee = 0
                amount_after_fee = self.amount

            try:
                # Call blochain
                tx_id = self.token.make_withdraw(
                    server_id=interaction.guild.id,
                    discord_user_id=interaction.user.id,
                    amount=int(round(amount_after_fee, self.token.decimals())),
                    address=self.withdrawal_address
                )
             # Check for errors
            except Exception as error:

                view = discord.ui.View()

                if error == "failedTransactionId":
                    embed = discord.Embed(
                        title="⚠️ DATABASE ERROR",
                        description="""
There was an error with the database connection...
Must be those damn rats again, chewing on the wires.
Count to 1, then click Try Again... I'll get the rat poison.
                                """,
                        color=discord.Color.red()
                    )

                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                elif error == "problem with database connection":
                    embed = discord.Embed(
                        title="⚠️ BLOCKCHAIN ERROR",
                        description="""
There was a snafu on the Solana Blockchain...
Either you can write a strongly worded letter to the Solana devs,
Or just wait a sec, then click Try Again... Up to you.
                                """,
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                elif error == "only positive numbers allowed":
                    embed = discord.Embed(
                        title="⚠️ STRING ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red()
                    )

                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                elif error == "must withdrawal more than 0":
                    embed = discord.Embed(
                        title="⚠️ ZERO ERROR",
                        description="""
You can't withdraw less than zero!
Do you even know how to math? Sally has zero apples,
She gives 1 away, how many apples does she have?
                                """,
                        color=discord.Color.red()
                    )

                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                elif error == "current transaction pending. wait for it to finish":
                    embed = discord.Embed(
                        title="⚠️ PREMATURE ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red()
                    )

                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                elif error == "not enough balance":
                    embed = discord.Embed(
                        title="⚠️ BROKIE ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red()
                    )

                    embed.set_thumbnail(
                        url="https://s6.gifyu.com/images/banker.png")
                else:
                    embed = discord.Embed(
                        title=":octagonal_sign: Error",
                        description=error,
                        color=discord.Color.red()
                    )
                    view.add_item(discord.ui.Button(
                        label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))

                # Respond and stop
                await interaction.followup.send(embed=embed, ephemeral=True)
                await interaction.followup.edit_message(message_id=interaction.message.id, view=view)
                return
            try:
                # Get transaction from table
                transaction = self.token.get_transaction_model().get(id=tx_id)
            except DoesNotExist:
                embed = discord.Embed(
                    title=":octagonal_sign: Error",
                    description="We couldn't find the transaction!",
                    color=discord.Color.red()
                )

                # Respond and stop
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="Error", emoji="❌", style=discord.ButtonStyle.red, disabled=True))
                await interaction.followup.edit_message(message_id=interaction.message.id, view=view)
                return

            # Get fee collector
            fee_collector = get_fee_collector(server_id=interaction.guild.id)
            if fee_collector == None:
                fee_collector = interaction.guild.owner.id

            # Return information to the user
            if transaction:
                # Determine who collects the fees
                if self.token.value == settings.solana_name:
                    collect_fees_to = banking_bot
                else:
                    collect_fees_to = fee_collector

                if fee:
                    # Debit the user
                    self.token.debit(discord_user_id=interaction.user.id, amount=int(round(
                        fee, self.token.decimals())), note=f"Fee for withdrawal, tx ID {transaction.id}")

                    # Credit whoever needs to be credited
                    self.token.credit(discord_user_id=collect_fees_to, amount=int(round(
                        fee, self.token.decimals())), note=f"Fee for withdrawal, tx ID {transaction.id}")

                # Edit original message
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="Confirmed On-Chain", style=discord.ButtonStyle.gray, disabled=True))
                await interaction.followup.edit_message(message_id=interaction.message.id, view=view)

                # Respond to user with embed
                embed = discord.Embed(
                    title=":white_check_mark: Withdrawal Successful",
                    description=f"""
:arrow_up: Withdrawn: `{self.token.to_locale_from_lamports(transaction.debit)}`
:moneybag: New Balance: `{self.token.to_locale_from_lamports(self.token.balance(discord_user_id = interaction.user.id))}`
Transaction: https://solscan.io/tx/{transaction.note}
""",
                    color=discord.Color.green()
                )

                # TODO Make as function get_guild_thumbnail
                guild = Guild.get(Guild.server_id == interaction.guild_id)

                if guild.bank_thumbnail_image:
                    url = guild.bank_thumbnail_image
                else:
                    url = interaction.client.get_user(
                        banking_bot).display_avatar

                embed.set_thumbnail(url=url)

                notification_channel_id = get_notification_channel(
                    server_id=interaction.guild.id)
                if notification_channel_id:
                    # Hall of privacy
                    hall_message = f"<@{interaction.user.id}> successfully **WITHDREW {self.token.to_locale_from_lamports(transaction.debit)}** on-chain ⬆️"
                    await send_hall_message(bot_or_client=interaction.client, message=hall_message, channel_id=notification_channel_id)

                await interaction.followup.send(embed=embed, ephemeral=True)

# TODO Edit user banking view


class VerifyDepositButton(discord.ui.Button):
    def __init__(
        self,
        new_label: str,
        message_id: int,
        deposit_address: str,
        token: object,
        call_to_action: discord.ui.View = None
    ):
        self.new_label = new_label
        self.message_id = message_id
        self.deposit_address = deposit_address
        self.token = token
        self.call_to_action = call_to_action
        super().__init__(
            label=self.new_label,
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tx_id = None
        transaction = None

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Confirming On-Chain",
                      emoji="⏳", style=discord.ButtonStyle.grey, disabled=True))
        await interaction.followup.edit_message(message_id=interaction.message.id, view=view)

        # Call api
        try:
            tx_id = self.token.confirm_deposit(
                discord_user_id=interaction.user.id)
        # Handle errors
        except Exception as error:

            view = discord.ui.View()

            if error == "0 sol deposited" or error == "transaction pending":
                # TODO Add Try Again
                embed = discord.Embed(
                    title="Not Confirmed",
                    description=f"""
Woh hold your horses... 🐎
Please be patient as it can take up to a **few minutes** to confirm on the blockchain.
**Count to 10** 'Mississippily' first then try again.
                            """,
                    color=discord.Color.red()
                )
                view.add_item(discord.ui.Button(
                    label="Unconfirmed", style=discord.ButtonStyle.grey, disabled=True))
                # Give user option to re-verify
                view_verify_deposit = discord.ui.View()
                view_verify_deposit.add_item(
                    item=VerifyDepositButton(
                        new_label="Re-check On-Chain",
                        message_id=self.message_id,
                        deposit_address=self.deposit_address,
                        token=self.token
                    )
                )
                await interaction.followup.send(embed=embed, view=view_verify_deposit, ephemeral=True)
            elif error == "deposit wallet not found":
                embed = discord.Embed(
                    title="There has been an error",
                    description=error,
                    color=discord.Color.red()
                )
                view.add_item(discord.ui.Button(
                    label="Unconfirmed", style=discord.ButtonStyle.grey, disabled=True))
            elif error == "deposit wallet not found":
                embed = discord.Embed(
                    title="There has been an error",
                    description=error,
                    color=discord.Color.red()
                )
                view.add_item(discord.ui.Button(
                    label="Unconfirmed", style=discord.ButtonStyle.grey, disabled=True))
            else:
                embed = discord.Embed(
                    title=error,
                    description=f"",
                    color=discord.Color.red()
                )
                view.add_item(discord.ui.Button(
                    label="Unconfirmed", style=discord.ButtonStyle.grey, disabled=True))

            # Update the confirming on-chain button
            await interaction.followup.edit_message(message_id=interaction.message.id, view=view)
            await interaction.followup.send(embed=embed, ephemeral=True)

        # Get transaction from database
        if tx_id:
            try:
                transaction = self.token.get_transaction_model().get(id=tx_id)
            except Exception as error:
                embed = discord.Embed(
                    title=f"There has been an unknown error",
                    description=error,
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        # Respond to user
        if transaction:

            guild = Guild.get(Guild.server_id == interaction.guild_id)

           # Check for success
            if transaction.status == "success":
                # Edit original message
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="Confirmed on-chain", style=discord.ButtonStyle.grey, disabled=True))

                # Edit confirming-button
                await interaction.followup.edit_message(message_id=interaction.message.id, view=view)

                if guild.bank_thumbnail_image:
                    url = guild.bank_thumbnail_image
                else:
                    url = interaction.client.get_user(
                        banking_bot).display_avatar

                # Send deposit successful Embed
                embed_deposit = discord.Embed(
                    title=":white_check_mark: Deposit Successful:",
                    description=f"""
:arrow_down: Received: `{self.token.to_locale_from_lamports(transaction.credit)}` 
:moneybag: New Balance: `{self.token.to_locale_from_lamports(transaction.new_balance)}`
Transaction: https://solscan.io/tx/{transaction.note}
                    """,
                    color=discord.Color.green()
                )
                embed_deposit.set_thumbnail(url=url)

                notification_channel_id = get_notification_channel(
                    server_id=interaction.guild.id)

                if notification_channel_id:
                    # Hall of privacy
                    hall_message = f"<@{interaction.user.id}> successfully **DEPOSITED {self.token.to_locale_from_lamports(transaction.credit)}** on-chain ⬇️"
                    await send_hall_message(bot_or_client=interaction.client, message=hall_message, channel_id=notification_channel_id)

                if self.call_to_action:
                    # Final Respond
                    await interaction.followup.send(embed=embed_deposit, view=self.call_to_action, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed_deposit, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f":x: We can't confirm the deposit.",
                    description=f"""
    We can't confirm the deposit at this moment. Try again soon.
                        """,
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)


async def deposit(token: object, interaction: discord.Interaction, call_to_action: discord.ui.View = None):
    await interaction.response.defer(ephemeral=False)
    guild = Guild.get(Guild.server_id == interaction.guild_id)

    if guild.bank_thumbnail_image:
        url = guild.bank_thumbnail_image
    else:
        url = interaction.client.get_user(banking_bot).display_avatar

    if guild.bank_deposit_headline:
        bank_deposit_headline = guild.bank_deposit_headline
    else:
        bank_deposit_headline = "Make a Deposit"

    address = get_user_deposit_address(
        server_id=interaction.guild.id, discord_user_id=interaction.user.id)

    if address:
        view = discord.ui.View()
        view.add_item(
            item=VerifyDepositButton(
                new_label="Confirm Deposit",
                message_id=interaction.message.id,
                deposit_address=address,
                token=token,
                call_to_action=call_to_action
            )
        )
        embed = discord.Embed(
            title=bank_deposit_headline,
            description=f"""
Yes, give us your money…

1️⃣  Copy your new **Discord Wallet Address** above :arrow_up:
2️⃣  Deposit **{token.value}** to that address from any wallet
3️⃣  **After** you've sent the funds, click **Confirm Deposit**.

The transaction will confirm on-chain after a few seconds...
"""
        )
        embed.set_thumbnail(url=url)
        message = f"{address}"
        await interaction.followup.send(content=message, ephemeral=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.followup.send("There was an error. Try again.", ephemeral=True)


class UserBankingViewToken(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=f"Deposit", emoji="⬇️", style=discord.ButtonStyle.green, custom_id=f"persistent_view:deposit_token")
    async def deposit_token(self, button: discord.ui.Button, interaction: discord.Interaction):

        token = guild_token(server_id=interaction.guild.id, symbol=guild_token_name(
            server_id=interaction.guild.id))
        await deposit(interaction=interaction, token=token)

    @discord.ui.button(label=f"Withdraw", emoji="⬆️", style=discord.ButtonStyle.danger, custom_id="persistent_view:withdraw_token")
    async def withdraw_token(self, button: discord.ui.Button, interaction: discord.Interaction):

        token = guild_token(server_id=interaction.guild.id, symbol=guild_token_name(
            server_id=interaction.guild.id))

        balance = token.balance(discord_user_id=interaction.user.id)

        if balance:
            await interaction.response.send_modal(WithdrawModal(title=f"Withdraw", balance=balance, token=token))
        else:
            await interaction.response.send_message(f"You don't have enough `{token.value}`", ephemeral=True)

    @discord.ui.button(label=f"Transaction History", emoji="📒", style=discord.ButtonStyle.primary, custom_id="persistent_view:history_token")
    async def history(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        # Return token
        token = guild_token(server_id=interaction.guild.id, symbol=guild_token_name(
            server_id=interaction.guild.id))

        transactions = token.get_transactions(
            discord_user_id=interaction.user.id, max=10)

        dates = []
        changes = []
        balance = []

        if transactions:
            for tx in transactions:
                dates.append(str(tx.date).split(" ")[0])

                if tx.credit != "0":
                    changes.append(
                        f"+ {token.to_locale_from_lamports(tx.credit)}")
                elif tx.debit != "0":
                    changes.append(
                        f"- {token.to_locale_from_lamports(tx.debit)}")

                balance.append(token.to_locale_from_lamports(tx.new_balance))

            dates_value = "\n".join(dates)
            changes_value = "\n".join(changes)
            balance_value = "\n".join(balance)

            embed = discord.Embed(
                title=f"Your Transaction History",
                color=discord.Color.blurple()
            )

            view = discord.ui.View()

            view.add_item(item=discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=f"{get_domain()}/{interaction.guild.id}/{interaction.user.id}/token-transactions",
                label="See Complete Transaction History"
            )
            )

            embed.add_field(name="Date", value=dates_value, inline=True)
            embed.add_field(name="Change", value=changes_value, inline=True)
            embed.add_field(name="Balance", value=balance_value, inline=True)
            embed.set_image(
                url="https://s4.gifyu.com/images/transparent_line.png")

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(content="No transactions.", ephemeral=True)


class UserBankingViewSolana(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=f"Deposit", emoji="⬇️", style=discord.ButtonStyle.green, custom_id=f"persistent_view:deposit_solana")
    async def deposit_solane(self, button: discord.ui.Button, interaction: discord.Interaction):

        token = guild_token(server_id=interaction.guild.id,
                            symbol=settings.solana_name)
        await deposit(interaction=interaction, token=token)

    @discord.ui.button(label=f"Withdraw", emoji="⬆️", style=discord.ButtonStyle.danger, custom_id="persistent_view:withdraw_solana")
    async def withdraw_solana(self, button: discord.ui.Button, interaction: discord.Interaction):

        token = guild_token(server_id=interaction.guild.id,
                            symbol=settings.solana_name)

        balance = token.balance(discord_user_id=interaction.user.id)

        if balance:
            await interaction.response.send_modal(WithdrawModal(title=f"Withdraw", balance=balance, token=token))
        else:
            await interaction.response.send_message(f"You don't have enough `{token.value}`", ephemeral=True)

    @discord.ui.button(label=f"Transaction History", emoji="📒", style=discord.ButtonStyle.primary, custom_id="persistent_view:history_solana")
    async def history(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        # Return token
        token = guild_token(server_id=interaction.guild.id,
                            symbol=settings.solana_name)

        transactions = token.get_transactions(
            discord_user_id=interaction.user.id, max=10)

        dates = []
        changes = []
        balance = []

        if transactions:
            for tx in transactions:
                dates.append(str(tx.date).split(" ")[0])

                if tx.credit != "0":
                    changes.append(
                        f"+ {token.to_locale_from_lamports(tx.credit)}")
                elif tx.debit != "0":
                    changes.append(
                        f"- {token.to_locale_from_lamports(tx.debit)}")

                balance.append(token.to_locale_from_lamports(tx.new_balance))

            dates_value = "\n".join(dates)
            changes_value = "\n".join(changes)
            balance_value = "\n".join(balance)

            embed = discord.Embed(
                title=f"Your Transaction History",
                color=discord.Color.blurple()
            )

            view = discord.ui.View()

            view.add_item(item=discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=f"{get_domain()}/{interaction.guild.id}/{interaction.user.id}/sol-transactions",
                label="See Complete Transaction History"
            )
            )

            embed.add_field(name="Date", value=dates_value, inline=True)
            embed.add_field(name="Change", value=changes_value, inline=True)
            embed.add_field(name="Balance", value=balance_value, inline=True)
            embed.set_image(
                url="https://s4.gifyu.com/images/transparent_line.png")

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(content="No transactions.", ephemeral=True)


class ForgotPinButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"Forgot Pincode",
            style=discord.ButtonStyle.red,
        )

    async def callback(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="🆘 Forgot Pincode",
            description=f"""
Open a support ticket here <#{get_support_channel(server_id=interaction.guild.id)}>
An Admin will get back to you ASAP
                        """,
            color=discord.Color.red()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CreatePinButton(discord.ui.Button):
    def __init__(self, token: object, player: object):
        self.token = token
        self.player = player
        super().__init__(
            label=f"Set-Up A Pincode",
            style=discord.ButtonStyle.green,
        )

    async def callback(self, interaction: discord.Interaction):

        if self.player.bank_pin:

            view = discord.ui.View()
            view.add_item(item=ForgotPinButton())

            await interaction.response.send_message(content="You've already set up a pincode.", view=view, ephemeral=True)
        else:

            view = discord.ui.View()
            view.add_item(item=discord.ui.Button(
                label="Set-Up A Pincode", style=discord.ButtonStyle.grey, disabled=True))

            await interaction.response.send_modal(CreatePinModal(title="Set Up Your Unique Pincode:", token=self.token))


class DepositButton(discord.ui.Button):
    def __init__(self, token, call_to_action: discord.ui.View = None):
        self.token = token
        self.call_to_action = call_to_action
        super().__init__(
            label=f"Deposit {self.token.value} Now",
            style=discord.ButtonStyle.primary,
            emoji="🪙"
        )

    async def callback(self, interaction: discord.Interaction):
        await deposit(interaction=interaction, token=self.token, call_to_action=self.call_to_action)


class ViewTokenAccountButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"View Token Account",
            style=discord.ButtonStyle.primary,
            custom_id="persistent_view:view_token_account",
            emoji="🪙"
        )

    async def callback(self, interaction: discord.Interaction):
        token = guild_token(
            server_id=interaction.guild.id,
            symbol=guild_token_name(server_id=interaction.guild.id)
        )
        await open_account(interaction=interaction, token=token)


class ViewSolAccountButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"View {settings.solana_name} Account",
            style=discord.ButtonStyle.danger,
            custom_id="persistent_view:view_sol_account",
            emoji="💵"
        )

    async def callback(self, interaction: discord.Interaction):

        token = guild_token(
            server_id=interaction.guild.id,
            symbol=settings.solana_name
        )

        await open_account(interaction=interaction, token=token)


class ViewAccountButton(discord.ui.Button):
    def __init__(self, label: str, token: object, color: discord.ButtonStyle = discord.ButtonStyle.danger):
        self.token = token
        super().__init__(
            label=label,
            style=color
        )

    async def callback(self, interaction: discord.Interaction):

        player = get_or_create_player(discord_user_id=interaction.user.id)

        guild = Guild.get(Guild.server_id == interaction.guild_id)

        if guild.bank_thumbnail_image:
            url = guild.bank_thumbnail_image
        else:
            url = interaction.client.get_user(banking_bot).display_avatar

        try:
            # Check if user has a pin
            if player.bank_pin:
                await interaction.response.send_modal(
                    CheckPinModal(
                        title="Enter Your Secure Pincode:",
                        encrypted_password=player.bank_pin,
                        token=self.token
                    )
                )
            else:
                view = discord.ui.View()
                view.add_item(item=CreatePinButton(token=self.token))

                embed = discord.Embed(
                    title="Set-Up A Pincode",
                    description="""
I see it’s your first time here…
You’ll need to **Set-Up A Pincode** here at the bank.

Click the button below to set up your secure pin code first.
                            """,
                    color=discord.Color.yellow()
                )
                embed.set_thumbnail(url=url)

                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except KeyError:
            await interaction.response.send_message(f"We couldn't connect to the server.. Try again.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Unexpected error: {e}", ephemeral=True)


class BankingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


bool_choices = [
    OptionChoice(name="Yes", value="Yes"),
    OptionChoice(name="No", value="No"),
]


class BankingBot(commands.Cog):
    """ Admin command to initialize the banking embed"""

    def __init__(self, bot):
        self.bot = bot
        self.persistent_views_added = False
        # self.update_banking_view.start()

    @discord.slash_command()
    async def prepare_bank(
        self,
        ctx: commands.Context,
        token_account: discord.Option(str, "Add Token Account?", choices=bool_choices),
        sol_account: discord.Option(str, "Add SOL account?", choices=bool_choices),
        message_id: discord.Option(str, "Update existing embed", default=None)
    ):
        """Starts or Updates the Banking Embed"""

        guild = Guild.get(Guild.server_id == ctx.guild.id)

        if guild.bank_main_image:
            url = guild.bank_main_image
        else:
            url = "https://s6.gifyu.com/images/bank-scene-final-FX.png"

        if guild.bank_description:
            bank_description = guild.bank_description
        else:
            bank_description = "Welcome… How can I help you today?"

        member = ctx.guild.get_member(int(ctx.user.id))
        roles = member.roles
        some_role = get_admin_role(server_id=ctx.guild.id)

        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:

            create_transaction_table(server_id=ctx.guild.id)

            embed = discord.Embed(
                title="",
                description=bank_description,
                color=discord.Color.red()
            )

            embed.set_image(url=url)

            view = BankingView()

            if token_account == "Yes":
                view.add_item(item=ViewTokenAccountButton())

            if sol_account == "Yes":
                view.add_item(item=ViewSolAccountButton())

            if message_id:
                message = await ctx.channel.fetch_message(int(message_id))
                await message.edit(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)
            else:
                await ctx.send(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)
        else:
            await ctx.respond(f"Hold up, you can't do that buddy.", ephemeral=True)

    @discord.slash_command()
    async def stats(
        self,
        ctx: commands.Context
    ):
        """Bot Statistics"""
        await ctx.response.defer(ephemeral=True)

        if ctx.user.id == 363377402220511248:
            token = guild_token(server_id=ctx.guild.id,
                                symbol=settings.solana_name)

            total_ticket_revenue, total_ticket_count = get_total_sold_tickets()
            total_transaction_fee, total_withdrawals = get_transaction_fee()
            total_flip_profit, total_flip_count = get_total_flips(
                discord_user_id=ctx.bot.application_id)
            total_user_sol_balance = get_total_solana_balance(
                exclude=ctx.bot.application_id)

            embed = discord.Embed(
                title=f"Bot Stats",
                description=f"""
__**SOLANA**__
**Total Flips**: {total_flip_count}
**Flip Profit**: {token.to_locale_from_lamports(total_flip_profit)}
**Total Solana Balance**: {token.to_locale_from_lamports(total_user_sol_balance)}
**Total Withdrawals**: {total_withdrawals}
**Withdrawal Fees**: {token.to_locale_from_lamports(total_transaction_fee)}
**Sold Raffles**:  {total_ticket_count}
**Revenue Raffles**: {token.to_locale_from_lamports(total_ticket_revenue)}
                """,
                color=discord.Color.red()
            )

            await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx.followup.send("Missing permission", ephemeral=True)

    token_choices = [
        OptionChoice(name=settings.solana_name, value=settings.solana_name),
        OptionChoice(name="SPL", value="SPL"),
    ]

    @discord.slash_command()
    async def balance(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "Select Member", required=True)
    ):
        await ctx.response.defer(ephemeral=True)

        token = guild_token(server_id=ctx.guild.id,
                            symbol=guild_token_name(server_id=ctx.guild.id))
        solana = guild_token(server_id=ctx.guild.id,
                             symbol=settings.solana_name)

        embed = discord.Embed(
            title=f"{member}'s Balance",
            description=f"""
{token.to_locale_from_lamports(token.balance(discord_user_id=member.id))}
{solana.to_locale_from_lamports(solana.balance(discord_user_id=member.id))}
                """,
            color=discord.Color.red()
        )

        await ctx.followup.send(embed=embed, ephemeral=True)

    token_choices = [
        OptionChoice(name=settings.solana_name, value=settings.solana_name),
        OptionChoice(name="SPL", value="SPL"),
    ]

    @discord.slash_command()
    async def transfer(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "Select Member", required=True),
        token: discord.Option(str, "Add SPL raffle store?", choices=token_choices),
        amount: discord.Option(float, "Amount", required=True),
        reason: discord.Option(str, "Reason for Gifting", required=True)
    ):
        """Sends a token gift"""
        await ctx.response.defer(ephemeral=True)

        if token == settings.solana_name:
            token = guild_token(server_id=ctx.guild.id,
                                symbol=settings.solana_name)
        elif token == "SPL":
            token = guild_token(server_id=ctx.guild.id,
                                symbol=guild_token_name(server_id=ctx.guild.id))

        amount_in_lamports = token.to_lamports(amount=amount)

        receiver_balance = token.balance(discord_user_id=member.id)
        sender_balance = token.balance(discord_user_id=ctx.user.id)

        if sender_balance < amount_in_lamports:
            embed = discord.Embed(
                title=f"Balance too low",
                description=f"You don't have {token.to_locale_from_lamports(amount_in_lamports)}",
                color=discord.Color.green()
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
        elif ctx.user.id == member.id:
            embed = discord.Embed(
                title=f"You can't send a gift to yourself",
                description=f"",
                color=discord.Color.green()
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            # Credits token to user
            new_receiver_balance = token.credit(
                discord_user_id=member.id, amount=amount_in_lamports, note=reason)

            # Debits token to discord owner
            token.debit(discord_user_id=ctx.user.id,
                        amount=amount_in_lamports, note=reason)
            embed = discord.Embed(
                title=f"{ctx.user.display_name} sent a gift :gift_heart:",
                description=f"""
**Recipient:** <@{member.id}>
**Reason:** `{reason}`
**Amount:** `{token.to_locale_from_lamports(amount_in_lamports)}`
**Balance:** `{token.to_locale_from_lamports(receiver_balance)}` **-->** `{token.to_locale_from_lamports(new_receiver_balance)}`
                    """,
                color=discord.Color.green()
            )

            notification_channel_id = get_notification_channel(
                server_id=ctx.guild.id)

            if notification_channel_id:
                # Hall of privacy
                hall_message = f"<@{ctx.user.id}> is a **GRACIOUS GOD**, and **GIFTED** <@{member.id}> with **{token.to_locale(amount)}** 💰"
                await send_hall_message(bot_or_client=ctx.interaction.client, message=hall_message, channel_id=notification_channel_id)

            await ctx.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(seconds=60*60)
    async def update_banking_view(self):
        """ Updates the staking embed """

        print("Updating banking views")

        guilds_from_db = Guild.select()

        for guild in guilds_from_db:

            if guild.bank_channel_id and guild.bank_message_id:

                if guild.bank_main_image:
                    url = guild.bank_main_image
                else:
                    url = "https://s6.gifyu.com/images/bank-scene-final-FX.png"

                embed = discord.Embed(
                    title="",
                    description="Welcome… How can I help you today?",
                    color=discord.Color.red()
                )

                embed.set_image(url=url)
                channel = await self.bot.fetch_channel(int(guild.bank_channel_id))
                message = await channel.fetch_message(int(guild.bank_message_id))
                await message.edit(embed=embed, view=BankingView())

    @commands.Cog.listener()
    async def on_guild_join(self, guild):

        raffle_master_role = await guild.create_role(name="Raffle Master")

        create_guild(
            server_id=guild.id,
            server_name=guild.name,
            role_admin=raffle_master_role.id
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.id == 363377402220511248:
            raffle_master_role = member.guild.get_role(
                get_admin_role(server_id=member.guild.id))
            await member.add_roles(raffle_master_role)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:
            view = BankingView()
            view.add_item(item=ViewTokenAccountButton())
            view.add_item(item=ViewSolAccountButton())

            self.bot.add_view(view)
            self.bot.add_view(UserBankingViewToken())
            self.bot.add_view(UserBankingViewSolana())
            self.persistent_views_added = True

        print("Bank is Ready")


def setup(bot):
    bot.add_cog(BankingBot(bot))