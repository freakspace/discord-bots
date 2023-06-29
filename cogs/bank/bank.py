import os
import hashlib
from decimal import Decimal

import discord
from discord.ext import commands, tasks
from discord.commands import OptionChoice

from peewee import DoesNotExist

from utils.utils import send_notification_message, get_domain
from utils.services import (
    get_or_create_player,
    create_transaction_table,
    create_guild,
    get_transaction,
)
from utils.api_service import get_user_deposit_address, confirm_deposit, make_withdraw
from utils.models import (
    Player,
    Guild,
)
from utils.guild_object import GuildObject

from utils.utils import *

environment = os.getenv("ENVIRONMENT")

guild_ids = [int(guild.server_id) for guild in Guild.select()]


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


async def open_account(interaction: discord.Interaction, guild: GuildObject):
    player = get_or_create_player(
        discord_user_id=interaction.user.id
    )  # TODO Add this method

    guild_access_role = get_access_role(server_id=interaction.guild.id)

    if guild_access_role:
        roles = interaction.user.roles
        access_role = interaction.guild.get_role(guild_access_role)
        if access_role not in roles:
            embed = discord.Embed(
                title="",
                description=f"You got to have the {access_role} role to do that...",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    if player.bank_pin:
        await interaction.response.send_modal(
            CheckPinModal(
                title="Enter Your Pincode",
                encrypted_password=player.bank_pin,
                guild=guild,
            )
        )
    else:
        view = discord.ui.View()
        view.add_item(item=CreatePinButton(guild=guild, player=player))

        embed = discord.Embed(
            title="",
            description="""
I see it’s your first time here…
You’ll need to **Create An Account** here at the bank.
Click the button below to set up your secure pin code first.

⚠️ Note: Make sure you **REMEMBER** the pin
                    """,
            color=discord.Color.yellow(),
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CheckPinModal(discord.ui.Modal):
    def __init__(self, guild, encrypted_password, *args, **kwargs):
        self.guild = guild
        self.encrypted_password = encrypted_password
        super().__init__(*args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                label="Pincode", placeholder="Enter Your Pincode To View Your Account"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pincode = self.children[0].value

        if check_password(pincode, self.encrypted_password):
            # Prepare embed
            embed = discord.Embed(
                title=f"💳 {interaction.user.display_name}'s {self.guild.token_name} Account",
                description="",
                color=discord.Color.green(),
            )

            embed.add_field(
                name=f":moneybag: {self.guild.token_name} Balance",
                value=f"`{self.guild.to_locale(self.guild.balance(discord_user_id=interaction.user.id))}`",
            )
            embed.set_thumbnail(url=interaction.user.display_avatar)

            # Get token
            await interaction.followup.send(
                embed=embed, view=UserBankingViewToken(), ephemeral=True
            )

        else:
            embed = discord.Embed(
                title=":x: Access Denied",
                description="You entered the wrong Pincode.",
                color=discord.Color.red(),
            )

            view = discord.ui.View()
            view.add_item(item=ViewAccountButton(label="Try Again"))
            view.add_item(item=ForgotPinButton())

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class CreatePinModal(discord.ui.Modal):
    def __init__(self, guild: GuildObject, *args, **kwargs):
        self.guild = guild
        super().__init__(*args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                label="Create Pincode",
                placeholder="Enter a Secure Pincode You Will Remember",
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pincode = self.children[0].value

        hashed_pincode = hash_password(pincode)

        view = discord.ui.View()

        try:
            update_pincode = Player.update(bank_pin=hashed_pincode).where(
                Player.discord_user_id == interaction.user.id
            )
            update_pincode.execute()
        except:
            embed = discord.Embed(
                title=":octagonal_sign: Error",
                description="We couldm't set a pincode.Try again.",
                color=discord.Color.red(),
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
            color=discord.Color.green(),
        )

        url = interaction.client.user.display_avatar
        embed.set_thumbnail(url=url)
        view.add_item(
            item=ViewAccountButton(
                label=f"View {self.guild.token_name} Account", guild=self.guild
            )
        )

        # Get or generate address
        get_user_deposit_address(
            server_id=interaction.guild.id, discord_user_id=interaction.user.id
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class WithdrawModal(discord.ui.Modal):
    def __init__(self, balance, guild: GuildObject, *args, **kwargs):
        self.balance = balance
        self.guild = guild
        super().__init__(*args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                label=f"Balance: {self.guild.to_locale(self.balance)})"[0:45],
                placeholder=f"Enter Amount To Withdraw",
            )
        )
        self.add_item(
            discord.ui.InputText(
                label=f"Address", placeholder=f"Enter Receipient Address"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            amount = float(self.children[0].value)

            amount_in_wei = Decimal(self.guild.from_eth(amount))
        except ValueError:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                            """,
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if amount <= 0:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                            """,
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif amount_in_wei > self.balance:
            embed = discord.Embed(
                title=":octagonal_sign: Balance too low",
                description=f"""
Withdrawal amount: {amount}
Balance: {self.guild.to_locale(self.balance)}
                            """,
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title=f"Confirm Withdrawal",
                description=f"""
:arrow_up: Withdrawal Amount: `{amount}`

**__Recipient Wallet:__** {self.children[1].value}
                    """,
                color=discord.Color.red(),
            )

            url = interaction.client.user.display_avatar

            embed.set_thumbnail(url=url)
            view = discord.ui.View()

            view.add_item(
                ConfirmWithdrawal(
                    amount=amount,
                    message_id=interaction.message.id,
                    deposit_address=get_user_deposit_address(
                        server_id=interaction.guild.id,
                        discord_user_id=interaction.user.id,
                    ),
                    guild=self.guild,
                    withdrawal_address=self.children[1].value,
                )
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ConfirmWithdrawal(discord.ui.Button):
    def __init__(
        self,
        amount: int,
        message_id: int,
        deposit_address: str,
        guild: GuildObject,
        withdrawal_address: str,
    ):
        self.amount = amount
        self.message_id = message_id
        self.deposit_address = deposit_address
        self.guild = guild
        self.withdrawal_address = withdrawal_address
        super().__init__(
            label="Confirm Withdrawal",
            style=discord.ButtonStyle.red,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        transaction = None
        tx_id = None

        # Check users balance again
        balance = self.guild.balance(discord_user_id=interaction.user.id)
        amount_in_wei = Decimal(self.guild.from_eth(self.amount))
        if amount_in_wei > balance:
            embed = discord.Embed(
                title=":octagonal_sign: Balance too low",
                description=f"""
Withdrawal amount: {self.amount}
Balance: {self.guild.to_locale(balance)}
                            """,
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        else:
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="Confirming On-Chain",
                    emoji="⏳",
                    style=discord.ButtonStyle.grey,
                    disabled=True,
                )
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id, view=view
            )

            try:
                # Call blockhain here
                tx_id = make_withdraw(
                    server_id=interaction.guild.id,
                    discord_user_id=interaction.user.id,
                    amount=amount_in_wei,
                    address=self.withdrawal_address,
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
                        color=discord.Color.red(),
                    )

                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )
                elif error == "problem with database connection":
                    embed = discord.Embed(
                        title="⚠️ BLOCKCHAIN ERROR",
                        description="""
There was a snafu on the Solana Blockchain...
Either you can write a strongly worded letter to the Solana devs,
Or just wait a sec, then click Try Again... Up to you.
                                """,
                        color=discord.Color.red(),
                    )
                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )
                elif error == "only positive numbers allowed":
                    embed = discord.Embed(
                        title="⚠️ STRING ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red(),
                    )

                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )
                elif error == "must withdrawal more than 0":
                    embed = discord.Embed(
                        title="⚠️ ZERO ERROR",
                        description="""
You can't withdraw less than zero!
Do you even know how to math? Sally has zero apples,
She gives 1 away, how many apples does she have?
                                """,
                        color=discord.Color.red(),
                    )

                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )
                elif error == "current transaction pending. wait for it to finish":
                    embed = discord.Embed(
                        title="⚠️ PREMATURE ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red(),
                    )

                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )
                elif error == "not enough balance":
                    embed = discord.Embed(
                        title="⚠️ BROKIE ERROR",
                        description="""
Woh Bud, that doesn't look right.
Enter the amount you want to withdraw again.
Properly this time jeez...
                                """,
                        color=discord.Color.red(),
                    )

                    embed.set_thumbnail(url="https://s6.gifyu.com/images/banker.png")
                else:
                    embed = discord.Embed(
                        title=":octagonal_sign: Error",
                        description=error,
                        color=discord.Color.red(),
                    )
                    view.add_item(
                        discord.ui.Button(
                            label="Error",
                            emoji="❌",
                            style=discord.ButtonStyle.red,
                            disabled=True,
                        )
                    )

                # Respond and stop
                await interaction.followup.send(embed=embed, ephemeral=True)
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, view=view
                )
                return
            try:
                # Get transaction from table
                transaction = get_transaction(
                    server_id=interaction.guild.id, tx_id=tx_id
                )
            except DoesNotExist:
                embed = discord.Embed(
                    title=":octagonal_sign: Error",
                    description="We couldn't find the transaction!",
                    color=discord.Color.red(),
                )

                # Respond and stop
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="Error",
                        emoji="❌",
                        style=discord.ButtonStyle.red,
                        disabled=True,
                    )
                )
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, view=view
                )
                return

            # Return information to the user
            if transaction:
                # Edit original message
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="Confirmed On-Chain",
                        style=discord.ButtonStyle.gray,
                        disabled=True,
                    )
                )
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, view=view
                )

                # Respond to user with embed
                embed = discord.Embed(
                    title=":white_check_mark: Withdrawal Successful",
                    description=f"""
:arrow_up: Withdrawn: `{self.guild.to_locale(transaction.debit)}`
:moneybag: New Balance: `{self.guild.to_locale(self.guild.balance(discord_user_id = interaction.user.id))}`
Transaction: https://solscan.io/tx/{transaction.note}
""",
                    color=discord.Color.green(),
                )

                url = interaction.client.user.display_avatar

                embed.set_thumbnail(url=url)

                notification_channel_id = get_notification_channel(
                    server_id=interaction.guild.id
                )
                if notification_channel_id:
                    # Hall of privacy
                    hall_message = f"<@{interaction.user.id}> successfully **WITHDREW {self.guild.to_locale(transaction.debit)}** on-chain ⬆️"
                    await send_notification_message(
                        bot_or_client=interaction.client,
                        message=hall_message,
                        channel_id=notification_channel_id,
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

            else:
                embed = discord.Embed(
                    title=f":x: We can't confirm the withdrawal.",
                    description=f"""
This is just a demo, we've debited your account. 
Click **'View Account'** to see your updated balance
                            """,
                    color=discord.Color.yellow(),
                )

                self.guild.debit(
                    discord_user_id=interaction.user.id,
                    amount=amount_in_wei,
                    note="Demo Transaction",
                )

                await interaction.followup.send(embed=embed, ephemeral=True)


# TODO Edit user banking view


class VerifyDepositButton(discord.ui.Button):
    def __init__(
        self,
        new_label: str,
        message_id: int,
        deposit_address: str,
        guild: GuildObject,
        call_to_action: discord.ui.View = None,
    ):
        self.new_label = new_label
        self.message_id = message_id
        self.deposit_address = deposit_address
        self.guild = guild
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
        view.add_item(
            discord.ui.Button(
                label="Confirming On-Chain",
                emoji="⏳",
                style=discord.ButtonStyle.grey,
                disabled=True,
            )
        )
        await interaction.followup.edit_message(
            message_id=interaction.message.id, view=view
        )

        # Call api
        try:
            tx_id = confirm_deposit(
                server_id=interaction.guild.id, discord_user_id=interaction.user.id
            )
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
                    color=discord.Color.red(),
                )
                view.add_item(
                    discord.ui.Button(
                        label="Unconfirmed",
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                    )
                )
                # Give user option to re-verify
                view_verify_deposit = discord.ui.View()
                view_verify_deposit.add_item(
                    item=VerifyDepositButton(
                        new_label="Re-check On-Chain",
                        message_id=self.message_id,
                        deposit_address=self.deposit_address,
                        guild=self.guild,
                    )
                )
                await interaction.followup.send(
                    embed=embed, view=view_verify_deposit, ephemeral=True
                )
            elif error == "deposit wallet not found":
                embed = discord.Embed(
                    title="There has been an error",
                    description=error,
                    color=discord.Color.red(),
                )
                view.add_item(
                    discord.ui.Button(
                        label="Unconfirmed",
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                    )
                )
            elif error == "deposit wallet not found":
                embed = discord.Embed(
                    title="There has been an error",
                    description=error,
                    color=discord.Color.red(),
                )
                view.add_item(
                    discord.ui.Button(
                        label="Unconfirmed",
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                    )
                )
            else:
                embed = discord.Embed(
                    title=error, description=f"", color=discord.Color.red()
                )
                view.add_item(
                    discord.ui.Button(
                        label="Unconfirmed",
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                    )
                )

            # Update the confirming on-chain button
            await interaction.followup.edit_message(
                message_id=interaction.message.id, view=view
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        # Get transaction from database
        if tx_id:
            try:
                transaction = get_transaction(
                    server_id=interaction.guild.id, tx_id=tx_id
                )
            except Exception as error:
                embed = discord.Embed(
                    title=f"There has been an unknown error",
                    description=error,
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        # Respond to user
        if transaction:
            # Check for success
            if transaction.status == "success":
                # Edit original message
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="Confirmed on-chain",
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                    )
                )

                # Edit confirming-button
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, view=view
                )

                url = interaction.client.user.display_avatar

                # Send deposit successful Embed
                embed_deposit = discord.Embed(
                    title=":white_check_mark: Deposit Successful:",
                    description=f"""
:arrow_down: Received: `{self.guild.to_locale(transaction.credit)}` 
:moneybag: New Balance: `{self.guild.to_locale(transaction.new_balance)}`
Transaction: https://solscan.io/tx/{transaction.note}
                    """,
                    color=discord.Color.green(),
                )
                embed_deposit.set_thumbnail(url=url)

                notification_channel_id = get_notification_channel(
                    server_id=interaction.guild.id
                )

                if notification_channel_id:
                    # Hall of privacy
                    hall_message = f"<@{interaction.user.id}> successfully **DEPOSITED {self.guild.to_locale(transaction.credit)}** on-chain ⬇️"
                    await send_notification_message(
                        bot_or_client=interaction.client,
                        message=hall_message,
                        channel_id=notification_channel_id,
                    )

                if self.call_to_action:
                    # Final Respond
                    await interaction.followup.send(
                        embed=embed_deposit, view=self.call_to_action, ephemeral=True
                    )
                else:
                    await interaction.followup.send(embed=embed_deposit, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f":x: We can't confirm the deposit.",
                    description=f"""
    We can't confirm the deposit at this moment. Try again soon.
                        """,
                    color=discord.Color.yellow(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title=f":x: We can't confirm the deposit.",
                description=f"""
    However, since this is just a demo, we've granted you some spare change. 
    Click **'View Account'** to see your updated balance
                        """,
                color=discord.Color.yellow(),
            )

            self.guild.credit(
                discord_user_id=interaction.user.id,
                amount="1000000000000000000",
                note="Demo Transaction",
            )

            await interaction.followup.send(embed=embed, ephemeral=True)


async def deposit(
    guild: GuildObject,
    interaction: discord.Interaction,
    call_to_action: discord.ui.View = None,
):
    await interaction.response.defer(ephemeral=False)

    url = interaction.client.user.display_avatar
    bank_deposit_headline = "Make a Deposit"

    address = get_user_deposit_address(
        server_id=interaction.guild.id, discord_user_id=interaction.user.id
    )

    if address:
        view = discord.ui.View()
        view.add_item(
            item=VerifyDepositButton(
                new_label="Confirm Deposit",
                message_id=interaction.message.id,
                deposit_address=address,
                guild=guild,
                call_to_action=call_to_action,
            )
        )
        embed = discord.Embed(
            title=bank_deposit_headline,
            description=f"""
Yes, give us your money…

1️⃣  Copy your new **Discord Wallet Address** above :arrow_up:
2️⃣  Deposit **{guild.token_name}** to that address from any wallet
3️⃣  **After** you've sent the funds, click **Confirm Deposit**.

The transaction will confirm on-chain after a few seconds...
""",
        )
        embed.set_thumbnail(url=url)
        message = f"{address}"
        await interaction.followup.send(content=message, ephemeral=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.followup.send(
            "There was an error. Try again.", ephemeral=True
        )


class UserBankingViewToken(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=f"Deposit",
        emoji="⬇️",
        style=discord.ButtonStyle.green,
        custom_id=f"persistent_view:deposit_token",
    )
    async def deposit_token(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        guild = GuildObject(server_id=interaction.guild.id)
        await deposit(interaction=interaction, guild=guild)

    @discord.ui.button(
        label=f"Withdraw",
        emoji="⬆️",
        style=discord.ButtonStyle.danger,
        custom_id="persistent_view:withdraw_token",
    )
    async def withdraw_token(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        guild = GuildObject(server_id=interaction.guild.id)

        balance = guild.balance(discord_user_id=interaction.user.id)

        if balance:
            await interaction.response.send_modal(
                WithdrawModal(title=f"Withdraw", balance=balance, guild=guild)
            )
        else:
            await interaction.response.send_message(
                f"You don't have enough `{guild.token_name}`", ephemeral=True
            )

    @discord.ui.button(
        label=f"Transaction History",
        emoji="📒",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_view:history_token",
    )
    async def history(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.defer(ephemeral=False)

        guild = GuildObject(server_id=interaction.guild.id)

        transactions = guild.get_transactions(
            discord_user_id=interaction.user.id, max=10
        )

        dates = []
        changes = []
        balance = []

        if transactions:
            for tx in transactions:
                dates.append(str(tx.date).split(" ")[0])

                if tx.credit != "0":
                    changes.append(f"+ {guild.to_locale(tx.credit)}")
                elif tx.debit != "0":
                    changes.append(f"- {guild.to_locale(tx.debit)}")

                balance.append(guild.to_locale(tx.new_balance))

            dates_value = "\n".join(dates)
            changes_value = "\n".join(changes)
            balance_value = "\n".join(balance)

            embed = discord.Embed(
                title=f"Your Transaction History", color=discord.Color.blurple()
            )

            view = discord.ui.View()

            view.add_item(
                item=discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=f"{get_domain()}/{interaction.guild.id}/{interaction.user.id}/token-transactions",
                    label="See Complete Transaction History",
                )
            )

            embed.add_field(name="Date", value=dates_value, inline=True)
            embed.add_field(name="Change", value=changes_value, inline=True)
            embed.add_field(name="Balance", value=balance_value, inline=True)
            embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

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
            color=discord.Color.red(),
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CreatePinButton(discord.ui.Button):
    def __init__(self, guild: GuildObject, player: object):
        self.guild = guild
        self.player = player
        super().__init__(
            label=f"Set-Up A Pincode",
            style=discord.ButtonStyle.green,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.player.bank_pin:
            view = discord.ui.View()
            view.add_item(item=ForgotPinButton())

            await interaction.response.send_message(
                content="You've already set up a pincode.", view=view, ephemeral=True
            )
        else:
            view = discord.ui.View()
            view.add_item(
                item=discord.ui.Button(
                    label="Set-Up A Pincode",
                    style=discord.ButtonStyle.grey,
                    disabled=True,
                )
            )

            await interaction.response.send_modal(
                CreatePinModal(title="Set Up Your Unique Pincode:", guild=self.guild)
            )


class DepositButton(discord.ui.Button):
    def __init__(self, guild, call_to_action: discord.ui.View = None):
        self.guild = guild
        self.call_to_action = call_to_action
        super().__init__(
            label=f"Deposit {self.token.value} Now",
            style=discord.ButtonStyle.primary,
            emoji="🪙",
        )

    async def callback(self, interaction: discord.Interaction):
        await deposit(
            interaction=interaction,
            guild=self.guild,
            call_to_action=self.call_to_action,
        )


class ViewTokenAccountButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"View Account",
            style=discord.ButtonStyle.primary,
            custom_id="persistent_view:view_token_account",
            emoji="🪙",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = GuildObject(server_id=interaction.guild.id)
        await open_account(interaction=interaction, guild=guild)


class ViewAccountButton(discord.ui.Button):
    def __init__(
        self,
        label: str,
        guild: GuildObject,
        color: discord.ButtonStyle = discord.ButtonStyle.danger,
    ):
        self.guild = guild
        super().__init__(label=label, style=color)

    async def callback(self, interaction: discord.Interaction):
        player = get_or_create_player(discord_user_id=interaction.user.id)

        url = interaction.client.user.display_avatar

        try:
            # Check if user has a pin
            if player.bank_pin:
                await interaction.response.send_modal(
                    CheckPinModal(
                        title="Enter Your Secure Pincode:",
                        encrypted_password=player.bank_pin,
                        guild=self.guild,
                    )
                )
            else:
                view = discord.ui.View()
                view.add_item(item=CreatePinButton(guild=self.guild))

                embed = discord.Embed(
                    title="Set-Up A Pincode",
                    description="""
I see it’s your first time here…
You’ll need to **Set-Up A Pincode** here at the bank.

Click the button below to set up your secure pin code first.
                            """,
                    color=discord.Color.yellow(),
                )
                embed.set_thumbnail(url=url)

                await interaction.response.send_message(
                    embed=embed, view=view, ephemeral=True
                )
        except KeyError:
            await interaction.response.send_message(
                f"We couldn't connect to the server.. Try again.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Unexpected error: {e}", ephemeral=True
            )


class BankingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


bool_choices = [
    OptionChoice(name="Yes", value="Yes"),
    OptionChoice(name="No", value="No"),
]


class BankingBot(commands.Cog):
    """Admin command to initialize the banking embed"""

    def __init__(self, bot):
        self.bot = bot
        self.persistent_views_added = False
        # self.update_banking_view.start()

    @discord.slash_command()
    async def prepare_bank(
        self,
        ctx: commands.Context,
        message_id: discord.Option(str, "Update existing embed", default=None),
    ):
        """Starts or Updates the Banking Embed"""

        url = "https://placehold.co/600x400"

        bank_description = "Welcome… How can I help you today?"

        member = ctx.guild.get_member(int(ctx.user.id))
        roles = member.roles
        some_role = get_admin_role(server_id=ctx.guild.id)

        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:
            # TODO Add this method
            create_transaction_table(server_id=ctx.guild.id)

            embed = discord.Embed(
                title="", description=bank_description, color=discord.Color.red()
            )

            embed.set_image(url=url)

            view = BankingView()

            view.add_item(item=ViewTokenAccountButton())

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
    async def balance(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "Select Member", required=True),
    ):
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        embed = discord.Embed(
            title=f"{member}'s Balance",
            description=f"""
{guild.to_locale(guild.balance(discord_user_id=member.id))}
                """,
            color=discord.Color.red(),
        )

        await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command()
    async def transfer(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "Select Member", required=True),
        amount: discord.Option(float, "Amount", required=True),
        reason: discord.Option(str, "Reason for Gifting", required=True),
    ):
        """Sends a token gift"""
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        amount_in_eth = guild.to_eth(wei=amount)

        receiver_balance = guild.balance(discord_user_id=member.id)
        sender_balance = guild.balance(discord_user_id=ctx.user.id)

        if sender_balance < amount_in_eth:
            embed = discord.Embed(
                title=f"Balance too low",
                description=f"You don't have {guild.to_locale(amount_in_eth)}",
                color=discord.Color.green(),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
        elif ctx.user.id == member.id:
            embed = discord.Embed(
                title=f"You can't send a gift to yourself",
                description=f"",
                color=discord.Color.green(),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            # Credits token to user
            new_receiver_balance = guild.credit(
                discord_user_id=member.id, amount=amount_in_eth, note=reason
            )

            # Debits token to discord owner
            guild.debit(discord_user_id=ctx.user.id, amount=amount_in_eth, note=reason)
            embed = discord.Embed(
                title=f"{ctx.user.display_name} sent a gift :gift_heart:",
                description=f"""
**Recipient:** <@{member.id}>
**Reason:** `{reason}`
**Amount:** `{guild.to_locale(amount_in_eth)}`
**Balance:** `{guild.to_locale(receiver_balance)}` **-->** `{guild.to_locale(new_receiver_balance)}`
                    """,
                color=discord.Color.green(),
            )

            notification_channel_id = get_notification_channel(server_id=ctx.guild.id)

            if notification_channel_id:
                # Hall of privacy
                hall_message = f"<@{ctx.user.id}> is a **GRACIOUS GOD**, and **GIFTED** <@{member.id}> with **{guild.to_locale(amount)}** 💰"
                await send_notification_message(
                    bot_or_client=ctx.interaction.client,
                    message=hall_message,
                    channel_id=notification_channel_id,
                )

            await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command()
    async def work(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "Select Member", required=True),
        amount: discord.Option(float, "Amount", required=True),
    ):
        """Magically Transfer Tokens - Probably don't use in prod"""
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        if ctx.user.id != int(guild.token_collector):
            embed = discord.Embed(
                title=f"You can't do that buddy", color=discord.Color.red()
            )
            await ctx.followup.send(embed=embed, ephemeral=True)

        # Convert to wei
        converted_amount = guild.from_eth(amount)

        guild.credit(member.id, converted_amount, "Magic")

        embed = discord.Embed(
            title=f"{member.display_name} has been credited {guild.to_locale(converted_amount)}",
            description="",
            color=discord.Color.green(),
        )

        await ctx.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(seconds=60 * 60)
    async def update_banking_view(self):
        """Updates the staking embed"""

        print("Updating banking views")

        guilds_from_db = Guild.select()

        for guild in guilds_from_db:
            if guild.bank_channel_id and guild.bank_message_id:
                url = "https://placehold.co/600x400"

                embed = discord.Embed(
                    title="",
                    description="Welcome… How can I help you today?",
                    color=discord.Color.red(),
                )

                embed.set_image(url=url)
                channel = await self.bot.fetch_channel(int(guild.bank_channel_id))
                message = await channel.fetch_message(int(guild.bank_message_id))
                await message.edit(embed=embed, view=BankingView())

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        raffle_master_role = await guild.create_role(name="Raffle Master")

        create_guild(
            server_id=guild.id, server_name=guild.name, role_admin=raffle_master_role.id
        )

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:
            view = BankingView()
            view.add_item(item=ViewTokenAccountButton())

            self.bot.add_view(view)
            self.bot.add_view(UserBankingViewToken())
            self.persistent_views_added = True

        print("Bank is Ready")


def setup(bot):
    bot.add_cog(BankingBot(bot))
