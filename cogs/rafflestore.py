
import datetime
import random

import pytz
import discord
from discord.ext import commands, tasks
from discord.commands import OptionChoice
from peewee import DoesNotExist

from utils.models import (
    Raffle,
    Receipt,
    Guild
)

from utils.utils import (
    get_access_role, 
    get_admin_role, 
    get_raffle_winner_channel, 
    get_mod_role
    )

from utils.services import (
    increment_or_create_receipt,
    increment_total_sold,
    create_raffle,
)

from utils.guild_object import GuildObject


utc = pytz.utc

guild_ids = [int(guild.server_id) for guild in Guild.select()]

# TODO Add basic options to edit
# TODO Add a hide raffle function
# TODO Interaction failed when trying to delete form a store without Raffles
# TODO Finish the hide raffle button
# TODO The bot should work out of the box
# TODO Auto add role rafflemaster
# TODO Edit message fails after deposit SOL
# TODO Schedule raffles / upcoming raffles
# TODO Fix pick winner
# TODO Add giveaway_channel_id
# TODO In giveaway print the winner name
# TODO In thread tag winner
# TODO tag the mod in giveaway channel and thread
# TODO Maybe limit the amount of ticket purchaseble
# TODO Probably want to double check add_raffle validation
# TODO SOL Raffles has to be picked in Degen Labz
# TODO Make a command to check which data is missing for each guild
# TODO Make make a test function to check for missing data, which is checked before at certain action is taken

  

def get_raffle(store_id: str, id: int):
    return Raffle.get(Raffle.store == store_id, Raffle.id == id)


def has_sale(store_id: str):
    """ Check if there is any raffle for sale """
    return Raffle.select().where(Raffle.store == store_id)


def check_has_time(timestamp):

    time_now = utc.localize(datetime.datetime.now())

    time_end = utc.localize(timestamp)

    if time_now > time_end:
        return False
    else:
        return True


def generate_item_embed(store_item: object):
    """ Generate one item embed """

    guild = GuildObject(server_id=store_item.server_id)

    embed = discord.Embed(
        title=store_item.title,
        description=store_item.description,
        color=discord.Color.green()
    )

    sold = store_item.sold

    embed.set_thumbnail(url=store_item.image_url)
    embed.add_field(name="Price", value=guild.to_locale(
        store_item.price), inline=True)
    embed.add_field(name="Sold", value=sold, inline=True)
    embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

    time_end = utc.localize(
        datetime.datetime.fromisoformat(str(store_item.duration)))

    time_end_unix = f"<t:{int(datetime.datetime.timestamp(time_end))}:R>"

    if not check_has_time(store_item.duration):
        embed.add_field(name="Closed", value=time_end_unix)
    else:
        embed.add_field(name="Closes", value=time_end_unix)

    return embed


def generate_stash_embed(store_item: object, owned: int):
    """ Generate one stash embed """

    guild = GuildObject(server_id=store_item.server_id)

    embed = discord.Embed(
        title=store_item.title,
        description=store_item.description,
        color=discord.Color.green()
    )

    embed.set_thumbnail(url=store_item.image_url)
    embed.add_field(name="Price", value=guild.to_locale(
        store_item.price), inline=True)
    embed.add_field(name="Owned", value=owned, inline=True)
    embed.set_image(url="https://s4.gifyu.com/images/transparent_line.png")

    time_now = utc.localize(datetime.datetime.now())

    try:
        time_end = utc.localize(
            datetime.datetime.fromisoformat(str(store_item.duration)))
        if time_now > time_end:
            embed.add_field(
                name="Closed", value=f"<t:{int(datetime.datetime.timestamp(time_end))}:R>")
        else:
            embed.add_field(
                name="Closes", value=f"<t:{int(datetime.datetime.timestamp(time_end))}:R>")
    except ValueError:
        """ In case date is set incorrectly in json """
        embed.add_field(name="\u200b", value="\u200b")

    return embed


def prepare_stash_embeds(discord_user_id: int) -> list:
    """Generate all the embeds and return as a list"""

    # TODO Not tested
    raffles = (Raffle
                   .select()
                   .join(Receipt, on=(Raffle.id == Receipt.raffle_id))
                   .where(
                    Receipt.discord_user_id == discord_user_id, Raffle.visible == True)
                   .order_by(Raffle.title)
                   .distinct())

    embeds = []

    for raffle in raffles:
        try:
            player_receipt = Receipt.select().where(
                Receipt.discord_user_id == discord_user_id, Receipt.raffle == raffle.id).get()

            embed = generate_stash_embed(
                store_item=raffle,
                owned=player_receipt.owned,
            )

            embeds.append(embed)
        except DoesNotExist:
            print(f"No receipt found for user_id {discord_user_id} and raffle_id {raffle.id}")

    return embeds


def check_sale_active(item: object):

    time_now = utc.localize(datetime.datetime.now())

    try:
        time_end = utc.localize(
            datetime.datetime.fromisoformat(str(item.duration)))
        if time_now > time_end:
            return False
        else:
            return True
    except ValueError:
        return False


def pick_winner(item_id: int, winners: int):
    store_receipts = (Receipt
                      .select()
                      .join(Raffle)
                      .order_by(Receipt.owned.desc())
                      .where(Raffle.id == item_id))

    choices = [receipt.user for receipt in store_receipts]
    weights = [receipt.owned for receipt in store_receipts]

    winners_list = []

    if len(choices) < winners:
        winners = len(choices)

    for _ in range(winners):
        idx, winner = random.choices(population=list(
            enumerate(choices)), weights=weights, k=1)[0]
        winners_list.append(winner)
        del choices[idx]
        del weights[idx]

    return winners_list


def generate_option(item: object):
    option = discord.SelectOption(
        label=item.title[0:99],
        value=str(item.id),
        description=f""
    )
    return option


async def check_has_role(interaction, role_id: int = None) -> bool:
    if role_id:
        role = interaction.guild.get_role(role_id)
        return role in interaction.user.roles
    else:
        return


async def delete_item(interaction, store_id: str, item_id: int, title: str):
    """ Deletes the Raffle and all Receipts (recursive=True) """
    raffle = get_raffle(store_id=store_id, id=item_id)
    raffle.delete_instance(recursive=True)
    await interaction.response.send_message(f"{title} has been deleted", ephemeral=True)


# TODO Test token here
async def buy_item(interaction, item: Raffle, quantity: int, guild: GuildObject):
    total_price = int(item.price) * quantity

    # Check if sale is active
    if not check_sale_active(item=item):
        message = f"""
            Hold on buddy, this sale is not longer available!"""
        await interaction.followup.send(message, ephemeral=True)
        return

    # Check if user has role
    role_id = get_access_role(server_id=interaction.guild.id)

    if role_id:
        if not await check_has_role(interaction=interaction, role_id=role_id):
            message = f"""
    Woh... You need the <@&{role_id}> role to buy anything here... 
    I could get into serious trouble for even talking to ya! 👀
    """
            await interaction.followup.send(message, ephemeral=True)
            return

    balance = int(guild.balance(discord_user_id=interaction.user.id))

    if balance < total_price:

        view = discord.ui.View()

        embed = discord.Embed(
            title=f"⚠️ LOW BALANCE",
            description=f"""
**__Current Balance:__** {guild.to_locale(balance)}
Hold up! You don't have enough {guild.token_name}!              
""",
            color=discord.Color.blurple()
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return

    elif balance >= total_price:

        # Debit the users balance
        guild.debit(
            discord_user_id=interaction.user.id,
            amount=total_price,
            note=f"Bought Raffle Ticket: {item.title} x {quantity}"
        )

        guild.credit(
            discord_user_id=guild.token_collector,
            amount=total_price,
            note=f"Sold Raffle Ticket: {item.title} x {quantity}"
        )

    # Calling database: Increment existing receipt or create a new one
    increment_or_create_receipt(
        discord_user_id=interaction.user.id,
        raffle=item,
        quantity=quantity
    )

    # Call db to increment total sold
    increment_total_sold(raffle=item, quantity=quantity)

    # Generate the embed
    winner_announcements = f"Winners will be announced in the <#{get_raffle_winner_channel(server_id=interaction.guild.id)}> channel soon"

    embed = discord.Embed(
        title=f"🎟️ {item.title}",
        description=f"""
**Congratulations!**
You are in the draw for **{item.title}**
{winner_announcements}
""",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="Price", value=guild.to_locale(int(item.price)))
    embed.add_field(name="Quantity",
                    value=quantity)
    embed.add_field(name="Grand Total",
                    value=guild.to_locale(total_price))

    embed.set_thumbnail(url=item.image_url)

    # Generate the view
    view = discord.ui.View()

    # Add one re-buy button to view
    view.add_item(
        item=BuyButton(
            item=item,
            guild=guild,
            label=f"Buy Another {quantity}x",
            quantity=quantity,
            disabled=False,
            color=discord.ButtonStyle.success
        )
    )

    # Respond
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class BuyButton(discord.ui.Button):
    """ Generate a buy button """

    def __init__(
        self,
        item: object,
        guild: GuildObject,
        quantity: int,
        label: str,
        disabled: bool,
        color: discord.ButtonStyle
    ):
        self.quantity = quantity
        self.item = item
        self.guild = guild
        self.color = color

        super().__init__(
            label=f"{label}",
            emoji="🎟️",
            style=self.color,
            disabled=disabled
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await buy_item(interaction, item=self.item, quantity=self.quantity, guild=self.guild)


class DeleteConfirmationButton(discord.ui.Button):
    """ Confirmation button to delete a Raffle """

    def __init__(self, store_id: str, item_id: int, title: str):
        self.store_id = store_id
        self.item_id = item_id
        self.title = title

        super().__init__(
            label=f"Confirm Deletion of {title}",
            emoji="❕",
            style=discord.ButtonStyle.danger
        )

    async def callback(self, interaction: discord.Interaction):
        await delete_item(interaction, store_id=self.store_id, item_id=self.item_id, title=self.title)


class SelectButton(discord.ui.Select):
    """ Generate a select button """

    def __init__(self, store: str):
        self.store = store
        self.raffles = Raffle.select().where(Raffle.store == self.store)

        super().__init__(
            placeholder=f"Select from the {self.store} store",
            min_values=1,
            max_values=1,
            options=[generate_option(item=raffle) for raffle in self.raffles]
        )


class DeleteSelectButton(SelectButton):
    def __init__(self, store: str):
        super().__init__(
            store=store
        )

    async def callback(self, interaction: discord.Interaction):

        raffle = Raffle.get(id=self.values[0])

        view = discord.ui.View()

        view.add_item(DeleteConfirmationButton(store_id=self.store,
                      item_id=self.values[0], title=raffle.title))

        await interaction.response.send_message("Danger! This action will permanently delete the Raffle and ALL associated Receipts", view=view, ephemeral=True)


class RaffleStashButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=f"Stash",
            style=discord.ButtonStyle.primary,
            custom_id="persistent_view:stash"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        embeds = prepare_stash_embeds(discord_user_id=interaction.user.id)

        if embeds:
            await interaction.followup.send(embeds=embeds, ephemeral=True)
        else:
            await interaction.followup.send("You don't have any items.", ephemeral=True)


class RaffleShowButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Raffles",
            style=discord.ButtonStyle.danger,
            custom_id="persistent_view:token_raffle"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = GuildObject(server_id=interaction.guild.id)

        store_items = Raffle.select().where(
            Raffle.server_id == interaction.guild.id,
            Raffle.visible == True
        )

        if store_items:
            for store_item in store_items:
                embed = generate_item_embed(store_item=store_item)
                view = discord.ui.View()
                if check_has_time(store_item.duration):
                    for n in [1, 10, 100]:
                        view.add_item(
                            item=BuyButton(
                                item=store_item,
                                guild=guild,
                                label=f"Buy {n}x",
                                quantity=n,
                                disabled=False,
                                color=discord.ButtonStyle.success
                            )
                        )
                else:
                    view.add_item(
                        item=BuyButton(
                            item=store_item,
                            guild=guild,
                            label=f"Closed",
                            quantity=1,
                            disabled=True,
                            color=discord.ButtonStyle.danger
                        )
                    )
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send("No items for sale, check back later!", ephemeral=True)


class RaffleStoreView(discord.ui.View):
    """ View that contains the different stores """

    def __init__(self):
        super().__init__(timeout=None)


class CreateItemModal(discord.ui.Modal):
    def __init__(self, guild: GuildObject, winners: int, *args, **kwargs) -> None:
        self.guild = guild
        self.winners = winners

        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Item Name"))
        self.add_item(discord.ui.InputText(
            label="Description", style=discord.InputTextStyle.long))
        self.add_item(discord.ui.InputText(
            label="Image URL (full image URL including https)"))
        self.add_item(discord.ui.InputText(label="Price (e.g. '100')"))
        self.add_item(discord.ui.InputText(
            label="Duration (e.g. '1 d' or '12 h')"))

    async def callback(self, interaction: discord.Interaction):
        # Get data
        item_name = self.children[0].value
        item_description = self.children[1].value
        item_image = self.children[2].value
        item_price = self.children[3].value
        item_duration = self.children[4].value

        # Check title
        if len(item_name) > 45:
            embed = discord.Embed(
                title="⚠️ TITLE TOO LONG",
                description=f"""
The title is too long. Max 45 characters

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check description
        if len(item_description) > 255:
            embed = discord.Embed(
                title="⚠️ DESCRIPTION TOO LONG",
                description=f"""
The description is too long. Max 255 characters

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # check price
        try:
            price = float(item_price)
        except ValueError:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
Try add a number.
Properly this time jeez...

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        item_duration_split = item_duration.split(" ")

        # Check time
        if len(item_duration_split) != 2:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Woh Bud, that doesn't look right.
It should look more like this '1 d'

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            int(item_duration_split[0])
        except ValueError:
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
First character has to be an integer

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if item_duration_split[1] != "d" and item_duration_split[1] != "h":
            embed = discord.Embed(
                title="⚠️ STRING ERROR",
                description=f"""
Last character has to be 'd' (for day) og 'h' (for hour)

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if item_image[0:8] != "https://":
            embed = discord.Embed(
                title="⚠️ URL ERROR",
                description=f"""
Make sure to include https:// in the image url

{item_name}
{item_description}
{item_image}
{item_price}
{item_duration}
                            """,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            # Create the raffle
            create_raffle(
                server_id=interaction.guild.id,
                title=item_name,
                description=item_description,
                image_url=item_image,
                price=self.guild.from_eth(price),
                duration=item_duration,
                winners=self.winners
            )
            await interaction.response.send_message("All done, item added.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)


class CreateRaffleButton(discord.ui.Button):
    def __init__(self, guild: GuildObject, winners: int):
        self.guild = guild
        self.winners = winners
        super().__init__(
            label=f"Create {self.guild.token_name} Raffle",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreateItemModal(title="Create Item", guild=self.guild, winners=self.winners))


class HideRaffleButton(discord.ui.Button):
    def __init__(self, raffle_id: int, raffle_name: str):
        self.raffle_id = raffle_id
        self.raffle_name = raffle_name
        super().__init__(
            label=f"Remove {self.raffle_name}",
            style=discord.ButtonStyle.red,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            Raffle.update(visible=False).where(
                Raffle.id == self.raffle_id).execute()

            await interaction.response.send_message(f"{self.raffle_name} has been removed", ephemeral=True)
        except:
            await interaction.response.send_message("There was an error, try again.", ephemeral=True)


bool_choices = [
    OptionChoice(name="Yes", value="Yes"),
    OptionChoice(name="No", value="No"),
]


class RaffleStore(commands.Cog):
    """ Admin command to initialize the store embed"""

    def __init__(self, bot):
        self.bot = bot
        self.persistent_views_added = False
        self.pick_winners.start()
        self.hide_raffles.start()

    @discord.slash_command()
    async def prepare_raffle(
        self,
        ctx: commands.Context,
        message_id: discord.Option(str, "Update existing embed", default=None)
    ):

        """Starts Raffle Store"""
        member = ctx.guild.get_member(int(ctx.user.id))
        roles = member.roles
        some_role = get_admin_role(server_id=ctx.guild.id)
        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:

            embed = discord.Embed(
                title="🎟️ Raffle Store",
                description=f"""
Buy Premium Raffles

Well what do ya want kid? 
I ain't got all day.
""",
                color=discord.Color.blurple()
            )

            embed.set_image(
                url="https://placehold.co/300x200?text=Placeholder")
            embed.set_thumbnail(
                url="https://placehold.co/300x200?text=Placeholder")

            view = RaffleStoreView()
            view.add_item(item=RaffleShowButton())
            view.add_item(item=RaffleStashButton())

            if message_id:
                message = await ctx.channel.fetch_message(int(message_id))
                await message.edit(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)
            else:
                message = await ctx.send(embed=embed, view=view)
                await ctx.respond(f"Updated.", ephemeral=True)

            # Update the guild raffle message and channel ID
            Guild.update(raffle_message_id=message.id, raffle_channel_id=ctx.channel.id).where(
                Guild.server_id == ctx.guild.id).execute()
        else:
            await ctx.respond("You can't do that", ephemeral=True)

    @discord.slash_command()
    async def add_raffle(
        self,
        ctx: commands.Context,
        winners: discord.Option(int, "How many winners?")
    ):
        """Create an item in the Raffle Store"""
        member = ctx.guild.get_member(int(ctx.user.id))
        roles = member.roles
        some_role = get_admin_role(server_id=ctx.guild.id)
        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:

            guild = GuildObject(server_id=ctx.guild.id)

            await ctx.response.send_modal(CreateItemModal(title="Create Item", guild=guild, winners=winners))

        else:
            await ctx.response.send_message(content="Nope.", ephemeral=True)

    # TODO Add rafflemaster role
    @discord.slash_command()
    async def remove_raffle(
        self,
        ctx: commands.Context
    ):

        view = discord.ui.View()

        raffles = Raffle.select().where(
            Raffle.server_id == ctx.guild.id, Raffle.visible == True)

        for raffle in raffles:
            view.add_item(item=HideRaffleButton(
                raffle_id=raffle.id, raffle_name=raffle.title))
        await ctx.response.send_message(view=view, ephemeral=True)

    @tasks.loop(seconds=60*60)
    async def hide_raffles(self):
        print("Hiding raffles")
        raffles = Raffle.select().where(Raffle.visible == True, Raffle.has_winner == True)
        if raffles:
            for raffle in raffles:
                delta = datetime.datetime.now() - raffle.duration

                # Hide raffles older than x days
                if delta.days >= 3:
                    Raffle.update(visible=False).where(
                        Raffle.id == raffle.id).execute()


    @tasks.loop(seconds=60*15)
    async def pick_winners(self):
        print("Picking winners")
        raffles = Raffle.select().where(Raffle.has_winner == False)
        if raffles:
            for raffle in raffles:
                if raffle.duration < datetime.datetime.now():
                    # Pick winners
                    winners_list = pick_winner(
                        item_id=raffle.id, winners=raffle.winners)
                    mentions = "\n".join(
                        [f"<@{winner.discord_user_id}>" for winner in winners_list])

                    # title for giveaway channel
                    title = f":tickets: **__{raffle.title} WINNER__** :tickets:"

                    # Message for giveaway channel
                    message = f"""
🎟 **__{raffle.title} WINNER__** 🎟 

🥳 **Congratulations Winner(s)!**
You have ⏰ `24 Hrs` To Claim Your Spot Before This Message is Deleted!!!

🎁 **__Your Prize:__** 
{raffle.title}!

**__How To Claim:__**
<@&{get_mod_role(server_id=raffle.server_id)}> will send you instructions.

🎉 **__Winner(s):__** 
{mentions}  
"""
                    # The message embed
                    message_embed = discord.Embed(
                        title=title,
                        description=message,
                        color=discord.Color.gold()
                    )

                    # Add image
                    image = raffle.image_url
                    message_embed.set_image(url=image)

                    # Send embed in giveaway channel
                    giveaway_channel_id = get_raffle_winner_channel(
                        server_id=raffle.server_id)

                    try:
                        giveaway_channel = await self.bot.fetch_channel(int(giveaway_channel_id))
                    except TypeError:
                        giveaway_channel = None

                    if giveaway_channel != None:
                        await giveaway_channel.send(embed=message_embed)

                    Raffle.update(has_winner=True, description=f"**WINNER HAS BEEN PICKED**\nThe winner(s) has been picked and announced in <#{giveaway_channel.id}>").where(
                        Raffle.id == raffle.id).execute()

                    # Only pick 1 at a time
                    return


    @discord.slash_command()
    async def magic(
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
                title=f"You can't do that buddy",
                color=discord.Color.red()
            )
            await ctx.followup.send(embed=embed, ephemeral=True)

        guild.credit(member.id, amount, "Magic")

        embed = discord.Embed(
            title=f"{member.display_name} has been credited {amount} {guild.token_name}",
            description="",
            color=discord.Color.green()
        )

        await ctx.followup.send(embed=embed, ephemeral=True)
    

    @discord.slash_command()
    async def balance(
        self,
        ctx: commands.Context,
        member: discord.Option(discord.Member, "(Optional) Select Member",  required=False),
        ):
        """Get balance of a player"""
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        if member:
            balance = guild.balance(member.id)
        else:
            balance = guild.balance(ctx.user.id)

        embed = discord.Embed(
            title=f"{member.display_name} has a balance of {guild.to_locale(balance)}",
            description="",
            color=discord.Color.green()
        )

        await ctx.followup.send(embed=embed, ephemeral=True)


    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:

            view = RaffleStoreView()
            view.add_item(item=RaffleShowButton())
            view.add_item(item=RaffleStashButton())

            self.bot.add_view(view)
            self.persistent_views_added = True

            await self.bot.change_presence(activity=discord.Game(name="💰SOL & SPL in Discord"))

        print("Rafflestore is ready")


def setup(bot):  # this is called by Pycord to setup the cog
    bot.add_cog(RaffleStore(bot))  # add the cog to the bot