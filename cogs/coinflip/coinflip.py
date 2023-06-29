import os
import random
from decimal import Decimal

import discord
from discord.ext import commands
from discord.commands import OptionChoice


from utils.utils import (
    get_admin_role,
    send_notification_message,
    get_notification_channel,
)
from utils.models import Guild
from utils.guild_object import GuildObject

from cogs.bank.bank import DepositButton

# TODO Buttons with actions without persistent view, grey them out.
# TODO Add deposit button when Balance too low
# TODO Create a function to check for admin role
# TODO Add bots balance to embeds

guild_ids = [int(guild.server_id) for guild in Guild.select()]

banking_bot = int(os.getenv("BANK_BOT_ID"))


def generate_option(symbol: str, amount: int):
    option = discord.SelectOption(
        label=f"{amount} {symbol}",
        value=str(amount),
        description=f"Flip for {amount} {symbol}",
    )
    return option


async def get_coinflip_result(
    interaction: discord.Interaction,
    amount: int,
    choice: str,
    guild: GuildObject,
):
    # Show the opposite of that the users selected
    result_mapping = {
        "Tails": "Heads",
        "Heads": "Tails",
    }

    client = interaction.client
    choices = ["Heads", "Tails"]
    winning_choice = random.choice(choices)
    print(f"Picking  {choice}")

    # Pick a winner
    if choice == winning_choice:
        winner = interaction.user.id
        loser = banking_bot
        result = choice
    else:
        winner = banking_bot
        loser = interaction.user.id
        result = result_mapping[choice]

    print(f"User picked {choice} and lost")
    print(f"Winner is {winner}")

    guild.credit(discord_user_id=winner, amount=amount, note="Won Coinflip")
    guild.debit(discord_user_id=loser, amount=amount, note="Lost Coinflip")

    notification_channel_id = get_notification_channel(server_id=interaction.guild.id)

    if winner == banking_bot:
        embed = discord.Embed(
            title=f"{client.get_user(loser).display_name} Lost",
            description="Sorry buddy... You lost!",
            color=discord.Color.red(),
        )

        embed.add_field(name="🏆 Result", value=result)
        embed.add_field(name=":cry: You Lost", value=guild.to_locale(amount))
        embed.add_field(
            name=":moneybag: Your New Balance",
            value=guild.to_locale(guild.balance(discord_user_id=loser)),
        )
        embed.set_thumbnail(url=client.get_user(loser).display_avatar)
        embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

        if notification_channel_id:
            hall_message = f"<@{interaction.user.id}> **FLIPPED** and **LOST** `{guild.to_locale(amount)}` :cry:"
            # Hall of privacy
            await send_notification_message(
                bot_or_client=interaction.client,
                message=hall_message,
                channel_id=notification_channel_id,
            )
        return embed
    elif winner == interaction.user.id:
        embed = discord.Embed(
            title=f"{client.get_user(winner).display_name} Won",
            description="Congratulations! You won!",
            color=discord.Color.green(),
        )
        embed.add_field(name="🏆 Result", value=result)
        embed.add_field(name=":tada: You Won", value=guild.to_locale(amount))
        embed.add_field(
            name=":moneybag: New Balance",
            value=guild.to_locale(guild.balance(discord_user_id=winner)),
        )
        embed.set_thumbnail(url=client.get_user(interaction.user.id).display_avatar)
        embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

        if notification_channel_id:
            hall_message = f"<@{interaction.user.id}> **FLIPPED** and **WON** `{guild.to_locale(amount)}` :tada:"
            # Hall of privacy
            await send_notification_message(
                bot_or_client=interaction.client,
                message=hall_message,
                channel_id=notification_channel_id,
            )

        return embed


class HeadsOrTailsButton(discord.ui.Button):
    def __init__(self, amount: int, choice: str, guild: GuildObject):
        self.amount = amount
        self.choice = choice
        self.guild = guild
        emojis = (
            {
                "Tails": "⏺️",
                "Heads": "⏹️",
            },
        )

        super().__init__(label=f"{choice}", emoji=emojis[0][choice])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Check user balance
        balance_user = self.guild.balance(discord_user_id=interaction.user.id)

        if self.amount > balance_user:
            view = discord.ui.View()
            view.add_item(
                item=DepositButton(guild=self.guild, call_to_action=self.view)
            )
            await interaction.followup.send(
                content=f"You only got {self.guild.to_locale(balance_user)} to play with..",
                view=view,
                ephemeral=True,
            )
            return

        # Disable buttons
        for child in self.view.children:
            child.disabled = True

        await interaction.followup.edit_message(
            message_id=interaction.message.id, view=self.view
        )

        # Get result
        result = await get_coinflip_result(
            interaction=interaction,
            amount=self.amount,
            choice=self.choice,
            guild=self.guild,
        )

        embeds = [result]
        view = discord.ui.View()

        # TODO Balance is also checked in the get_coinflip_result
        # Check user balance again
        balance_user = self.guild.balance(discord_user_id=interaction.user.id)

        if balance_user > self.amount:
            embed = discord.Embed(
                title=f"",
                description=f"""
<@{interaction.user.id}> You wanna go again for {self.guild.to_locale(self.amount)}? 
**Heads or Tail**?
                        """,
                color=discord.Color.greyple(),
            )

            # Only play again if user has a balance greater than the amount
            embeds.append(embed)

            view.add_item(
                HeadsOrTailsButton(
                    amount=self.amount,
                    choice="Heads",
                    guild=self.guild,
                )
            )
            view.add_item(
                HeadsOrTailsButton(
                    amount=self.amount,
                    choice="Tails",
                    guild=self.guild,
                )
            )

        await interaction.followup.send(embeds=embeds, view=view, ephemeral=True)


async def start_flip(
    interaction: discord.Interaction,
    guild: GuildObject,
    amount: float,
):
    amount_in_eth = Decimal(guild.from_eth(eth=amount))

    # Check balance is greater than 0
    if amount_in_eth <= 0:
        await interaction.followup.send(
            "Yo, we can't do that. Amount has to be greater than 0", ephemeral=True
        )
        return

    # Check user balance
    balance_user = Decimal(guild.balance(discord_user_id=interaction.user.id))

    if amount_in_eth > balance_user:
        # Send flip button as CTA after successful deposit
        cta_view = discord.ui.View()
        cta_view.add_item(item=StartFlipButton())

        view = discord.ui.View()
        view.add_item(item=DepositButton(guild=guild, call_to_action=cta_view))

        await interaction.followup.send(
            content=f"You only got {guild.to_locale(balance_user)} to play with..",
            view=view,
            ephemeral=True,
        )
        return

    # Check opponent balance
    balance_challengee = guild.balance(discord_user_id=banking_bot)
    if amount_in_eth > balance_challengee:
        embed = discord.Embed(
            title="",
            description=f"""
<@{banking_bot}> doesn't have {guild.to_locale(amount_in_eth)} to flip with!
            """,
            color=discord.Color.red(),
        )
        embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    embed = discord.Embed(
        title=f"Flip {guild.to_locale(amount_in_eth)} Against Flipper Floyd",
        description="Do you have what it takes to win against Flipper Floyd?",
        color=discord.Color.greyple(),
    )
    embed.set_thumbnail(url="https://placehold.co/600x400")
    embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

    view = discord.ui.View()
    view.add_item(
        HeadsOrTailsButton(
            amount=amount_in_eth,
            choice="Heads",
            guild=guild,
        )
    )
    view.add_item(
        HeadsOrTailsButton(
            amount=amount_in_eth,
            choice="Tails",
            guild=guild,
        )
    )
    embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class FlipButton(discord.ui.Button):
    def __init__(self, guild: GuildObject, amount: float):
        self.guild = guild
        self.amount = amount
        super().__init__(label=f"{self.amount} {self.guild.token_name}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await start_flip(interaction, self.guild, amount=self.amount)


class StartFlipButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"Flip",
            emoji="🪙",
            custom_id=f"persistent_view:flip_token_button",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = GuildObject(server_id=interaction.guild.id)

        view = discord.ui.View()

        flip_values = [
            1,
            10,
            100,
        ]

        for flip_value in flip_values:
            view.add_item(item=FlipButton(guild=guild, amount=flip_value))

        await interaction.followup.send(view=view, ephemeral=True)


bool_choices = [
    OptionChoice(name="Yes", value="Yes"),
    OptionChoice(name="No", value="No"),
]


class Coinflip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.persistent_views_added = False

    @discord.slash_command()
    async def prepare_coinflip(
        self,
        ctx: commands.Context,
        message_id: discord.Option(str, "Update existing embed", default=None),
    ):
        """Prepares the Flip Embed"""

        member = ctx.guild.get_member(int(ctx.user.id))

        roles = member.roles

        some_role = get_admin_role(server_id=ctx.guild.id)

        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:
            view = discord.ui.View(timeout=None)

            view.add_item(item=StartFlipButton())

            embed = discord.Embed(
                title="FLIP BOT",
                description="Spend your hard earned Discord Cash against the house",
                color=discord.Color.greyple(),
            )

            embed.set_thumbnail(url="https://placehold.co/600x400")
            embed.set_image(url="https://placehold.co/600x400")

            if message_id:
                message = await ctx.channel.fetch_message(int(message_id))
                await message.edit(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)
            else:
                await ctx.send(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)
        else:
            await ctx.respond("You can't do that", ephemeral=True)

    @discord.slash_command()
    async def flip(
        self,
        ctx: commands.Context,
        amount: discord.Option(float, "Choose an amount", required=True),
    ):
        """Flip Your Heart Out"""
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        await start_flip(
            interaction=ctx.interaction,
            guild=guild,
            amount=float(amount),
        )

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:
            view = discord.ui.View(timeout=None)
            view.add_item(item=StartFlipButton())
            self.bot.add_view(view)
            self.persistent_views_added = True

        print("Flip is Ready")


def setup(bot):
    bot.add_cog(Coinflip(bot))
