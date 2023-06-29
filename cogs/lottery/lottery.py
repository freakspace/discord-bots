import pytz
import json
import os
import datetime

from peewee import DoesNotExist

from utils.lottery import (
    get_lottery_numbers,
    pick_winning_numbers,
    calculate_prize_table,
    computes_prizes,
    find_correct_numbers,
)
from utils.utils import generate_option
from utils.guild_object import GuildObject
from utils.exceptions import InsufficientFunds

import discord
from discord.ext import commands, tasks
from discord.commands import OptionChoice

from utils.utils import (
    get_admin_role,
    get_raffle_winner_channel,
    get_notification_channel,
    send_notification_message,
)
from utils.models import (
    Lottery,
    LotteryNumber,
)

from utils.services import (
    start_new_lottery,
    create_lottery_ticket,
    increment_lottery_total_sold,
)

utc = pytz.utc

# TODO Automatically set end time when a minimum prize pool is met
# TODO Should be possible to define how often a lottery ends
# TODO Winnings more than 5 SOL should be manually verified
# TODO Make check balance a global function
# TODO balance is getting called very often
# TODO Add a "buy all 5x" button
# TODO The next lottery, does it have correct amount of days?
# TODO Add bonus without balance will still add the bonus


banking_bot = int(os.getenv("BANK_BOT_ID"))


def generate_list_to_string(list: list):
    return " - ".join(str(x) for x in list)


async def end_lottery(bot):
    # Filter lotteries without numbers picked
    lotteries = Lottery.select().where(Lottery.numbers_picked.is_null(True))

    for lottery in lotteries:
        # Check if end time has passed

        if lottery.end_time < datetime.datetime.now():
            # Pick winning numbers
            winning_numbers = pick_winning_numbers(lottery_id=lottery.id)

            # Loop through all lottery tickets and find the correct numbers
            find_correct_numbers(lottery_id=lottery.id)

            # Calculate, save and return prize table
            prize_table = calculate_prize_table(lottery=lottery)

            # Calculate total unclaimed
            unclaimed = 0
            for bucket in prize_table:
                if prize_table[bucket]["winners"] == 0:
                    unclaimed += prize_table[bucket]["total"]

            # Store prize amount on each lottery ticket
            computes_prizes(lottery_id=lottery.id, prize_table=prize_table)

            if prize_table[5]["winners"] == 0:
                jackpot_bonus = lottery.jackpot_bonus
            else:
                jackpot_bonus = "0"

            # Create a new lottery
            start_new_lottery(
                server_id=lottery.server_id,
                end_time=7,
                price=lottery.price,
                price_pool=str(round(unclaimed)),
                jackpot_bonus=jackpot_bonus,
            )

            # Send message in giveaway channel
            giveaway_channel_id = get_raffle_winner_channel(server_id=lottery.server_id)

            try:
                giveaway_channel = await bot.fetch_channel(int(giveaway_channel_id))
            except TypeError:
                giveaway_channel = None

            if giveaway_channel != None:
                prize_table = generate_prize_table(
                    lottery_id=lottery.id, guild_id=lottery.server_id
                )
                await giveaway_channel.send(embed=prize_table)

            notification_channel_id = get_notification_channel(
                server_id=lottery.server_id
            )

            if notification_channel_id:
                # Hall of privacy
                hall_message = f":moneybag: Lottery numbers **HAS BEEN PICKED!** :arrow_right:  `{generate_list_to_string(winning_numbers)}`"
                await send_notification_message(
                    bot_or_client=bot,
                    message=hall_message,
                    channel_id=notification_channel_id,
                )


def generate_prize_table(lottery_id: int, guild_id: int):
    lottery = Lottery.get(lottery_id)

    guild = GuildObject(server_id=guild_id)

    prize_table = json.loads(lottery.prize_table)

    time_end = utc.localize(datetime.datetime.fromisoformat(str(lottery.end_time)))
    time_end_unix = f"<t:{int(datetime.datetime.timestamp(time_end))}:R>"

    if lottery.jackpot_bonus != "0":
        bonus = int(lottery.jackpot_bonus)
    else:
        bonus = 0
    # Calculate total unclaimed
    claimed_bonus = 0
    total = 0
    unclaimed = 0

    for bucket in prize_table:
        total += prize_table[bucket]["total"]
        claimed_bonus += prize_table[bucket]["bonus"]

        if prize_table[bucket]["winners"] == 0:
            unclaimed += prize_table[bucket]["total"]

    # Message for giveaway channel
    title = f":tada: **LOTTERY NUMBERS PICKED** :tada: "
    description = f"""
The lottery **HAS ENDED** {time_end_unix} and the winning numbers has been picked!

**THE WINNING NUMBERS ARE**
`{generate_list_to_string(json.loads(lottery.numbers_picked))}`

**Prize Pool**
`{guild.to_locale(total)}` **+** `{guild.to_locale(bonus)}`

**Rewarded**
`{guild.to_locale(total + claimed_bonus - unclaimed)}`

**Going to next lottery** :arrow_right:
`{guild.to_locale(unclaimed)}` **+** `{guild.to_locale(bonus - claimed_bonus)}`

** PRIZE TABLE** ⬇️
    """

    embed = discord.Embed(
        title=title, description=description, color=discord.Color.gold()
    )

    embed.set_footer(
        text="Remember to claim your rewards by clicking 'View My Coupons' in the lottery"
    )

    numbers_mapping = {
        "5": "5️⃣ x Correct",
        "4": "4️⃣ x Correct",
        "3": "3️⃣ x Correct",
        "2": "2️⃣ x Correct",
        "1": "1️⃣ x Correct",
    }

    numbers = []
    winners = []
    prize = []

    for idx in reversed(prize_table):
        numbers.append(str(numbers_mapping[idx]))
        winners.append(str(prize_table[idx]["winners"]))
        prize.append(guild.to_locale(prize_table[idx]["prize"]))
    numbers_value = "\n".join(numbers)
    winners_value = "\n".join(winners)
    prize_value = "\n".join(prize)

    embed.add_field(name="\u200b", value=numbers_value, inline=True)
    embed.add_field(name="# Winners", value=winners_value, inline=True)
    embed.add_field(name="Prize pr. Winner", value=prize_value, inline=True)

    return embed


async def buy_lottery(
    interaction: discord.Interaction, lottery: object, numbers: list, guild: GuildObject
):
    if datetime.datetime.now() > lottery.end_time:
        message = f"""
**Lottery Has Ended**
Hold up, Degen! This lottery has already ended.
"""
        # TODO Send deposit button here
        await interaction.followup.send(content=message, ephemeral=True)
        return

    total_price = int(lottery.price)

    # Check user balance
    balance = guild.balance(discord_user_id=interaction.user.id)

    if balance < total_price:
        message = f"""
**__Current Balance:__** {guild.to_locale(balance)}
Hold up Degen! You don't have enough {guild.token_name}!
"""
        # TODO Send deposit button here
        await interaction.followup.send(content=message, ephemeral=True)
        return
    elif balance >= total_price:
        # Debit the users balance
        guild.debit(
            discord_user_id=interaction.user.id,
            amount=total_price,
            note=f"Bought Lottery Numbers {generate_list_to_string(list=numbers)}",
        )

        # Credit prize pool to the bot
        guild.credit(
            discord_user_id=banking_bot,
            amount=total_price,
            note=f"To prize pool for Lottery #{lottery.id}",
        )

    # Create lottery ticket
    create_lottery_ticket(
        discord_user_id=interaction.user.id, lottery_id=lottery.id, numbers=numbers
    )

    # Call db to increment total sold
    increment_lottery_total_sold(lottery_id=lottery.id, amount=total_price)

    time_end = utc.localize(datetime.datetime.fromisoformat(str(lottery.end_time)))
    time_end_unix = f"<t:{int(datetime.datetime.timestamp(time_end))}:R>"

    # Generate the embed
    embed = discord.Embed(
        title=f"🎟️ You're in the draw!",
        description=f"""
**Your Numbers**: `{generate_list_to_string(list=numbers)}`
**Time until draw**: {time_end_unix}

Winners will be announced in <#{get_raffle_winner_channel(server_id=interaction.guild.id)}>
""",
        color=discord.Color.green(),
    )

    embed.set_image(url="https://s4.gifyu.com/images/ticket-final-5x-lottery-small.png")

    # Generate the view
    view = discord.ui.View()

    # Add one re-buy button to view
    view.add_item(item=GenerateCoupons(label="Buy Another"))

    # Hall of privacy
    notification_channel_id = get_notification_channel(server_id=interaction.guild.id)

    if notification_channel_id:
        hall_message = f"<@{interaction.user.id}> just bought a **LOTTERY TICKET** :tickets: from <#{interaction.channel_id}>"
        await send_notification_message(
            bot_or_client=interaction.client,
            message=hall_message,
            channel_id=notification_channel_id,
        )

    # Respond
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class BuyCouponButton(discord.ui.Button):
    def __init__(self, lottery: object, numbers: list, guild: GuildObject):
        self.lottery = lottery
        self.numbers = numbers
        self.guild = guild

        super().__init__(
            label=generate_list_to_string(list=self.numbers),
            style=discord.ButtonStyle.danger,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Disable buttons
        for child in self.view.children:
            child.disabled = True

        self.style = discord.ButtonStyle.green
        self.emoji = "✅"

        await interaction.followup.edit_message(
            message_id=interaction.message.id, view=self.view
        )

        await buy_lottery(
            interaction=interaction,
            lottery=self.lottery,
            numbers=self.numbers,
            guild=self.guild,
        )


""" class ViewPrizes(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="View Prizes",
            style=discord.ButtonStyle.danger,
            custom_id="persistent_view:view_prizes"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(embed=embed, ephemeral=True) """


class ClaimRewards(discord.ui.Button):
    def __init__(self, lottery_id: int, guild: GuildObject, total_prize: int):
        self.lottery_id = lottery_id
        self.guild = guild
        self.total_prize = total_prize
        super().__init__(label="Claim Rewards", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        LotteryNumber.update(prize_claimed=True).where(
            LotteryNumber.lottery_id == self.lottery_id,
            LotteryNumber.discord_user_id == interaction.user.id,
        ).execute()

        self.guild.credit(
            discord_user_id=interaction.user.id,
            amount=self.total_prize,
            note=f"Total rewards from {self.guild.token_name} lottery #{self.lottery_id}",
        )

        self.guild.debit(
            discord_user_id=banking_bot,
            amount=self.total_prize,
            note=f"Rewarded {interaction.user.display_name} with rewards from lottery #{self.lottery_id}",
        )

        embed = discord.Embed(
            title=f"✅ Claimed",
            description=f"""
            You've successfully claimed your rewards

            Balance incremented by **+ {self.guild.to_locale(self.total_prize)}**
            """,
            color=discord.Color.green(),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)


class ViewCouponsSelectButton(discord.ui.Select):
    def __init__(self, lotteries: list):
        self.lotteries = lotteries
        super().__init__(
            placeholder=f"Select a lottery",
            min_values=1,
            max_values=1,
            options=[
                generate_option(
                    title=f"Lottery #{lottery.lottery_id}",
                    value=lottery.lottery_id,
                    description="",
                )
                for lottery in self.lotteries
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        lottery = Lottery.get(int(self.values[0]))

        coupons = LotteryNumber.select().where(
            LotteryNumber.discord_user_id == interaction.user.id,
            LotteryNumber.lottery_id == int(self.values[0]),
        )

        guild = GuildObject(server_id=interaction.guild.id)

        total_prize = 0

        claimable = False

        numbers = []
        claimed = []
        prizes = []

        for coupon in coupons[:20]:
            if lottery.numbers_picked is not None:
                if not coupon.prize_claimed:
                    claimable = True

            prize = coupon.get_prize()

            if prize:
                prize = int(prize)
                prizes.append(guild.to_locale(prize))
                total_prize += prize
            else:
                prize = "⌛"
                prizes.append(prize)

            numbers.append(generate_list_to_string(coupon.get_numbers()))
            claimed.append(coupon.get_claimed())

        # Only show max 20
        if len(coupons) > 20:
            numbers.append(f"**And {len(coupons) - 20} more coupons...**")
            # Continue counting
            for coupon in coupons[20:]:
                if prize:
                    total_prize += int(prize)

        numbers_value = "\n\n".join(numbers)
        claimed_value = "\n\n".join(claimed)
        prizes_value = "\n\n".join(prizes)

        embeds = []

        embed = discord.Embed(
            title="Your Lottery Numbers", color=discord.Color.blurple()
        )

        embed.add_field(name="Numbers", value=numbers_value, inline=True)
        embed.add_field(name="Claimed", value=claimed_value, inline=True)
        embed.add_field(name="Prize", value=prizes_value, inline=True)

        embeds.append(embed)

        # Show total rewards
        if total_prize > 0:
            embed = discord.Embed(
                title="Winner! :tada:",
                description=f"""
Congratulations, you lucky champ!

**Your** __**Total**__ **Rewards**: {guild.to_locale(total_prize)}
                """,
                color=discord.Color.green(),
            )
            embeds.append(embed)

            # Claim button
            view = discord.ui.View()

            if claimable:
                view.add_item(
                    item=ClaimRewards(
                        lottery_id=lottery.id, guild=guild, total_prize=total_prize
                    )
                )

                await interaction.followup.send(
                    embeds=embeds, view=view, ephemeral=True
                )
            else:
                await interaction.followup.send(embeds=embeds, ephemeral=True)
        else:
            await interaction.followup.send(embeds=embeds, ephemeral=True)


class ViewPlayerCoupons(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="View My Coupons",
            style=discord.ButtonStyle.danger,
            custom_id="persistent_view:solana_user_coupons",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = discord.ui.View()

        lotteries = (
            LotteryNumber.select(LotteryNumber.lottery_id)
            .distinct()
            .where(LotteryNumber.discord_user_id == interaction.user.id)
        )

        if len(lotteries) > 0:
            view.add_item(item=ViewCouponsSelectButton(lotteries=lotteries))
            await interaction.followup.send(view=view)
        else:
            await interaction.followup.send(
                content="You don't have any Lottery Coupons", ephemeral=True
            )


def generate_coupon_view(lottery: object, guild: GuildObject, view=discord.ui.View):
    # Generate numbers
    for _ in range(5):
        numbers = get_lottery_numbers()
        view.add_item(
            item=BuyCouponButton(lottery=lottery, numbers=numbers, guild=guild)
        )
    view.add_item(item=RefreshCoupons(lottery=lottery, guild=guild))
    return view


class RefreshCoupons(discord.ui.Button):
    def __init__(self, lottery: object, guild: GuildObject):
        self.lottery = lottery
        self.guild = guild
        super().__init__(label="Refresh", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = generate_coupon_view(
            lottery=self.lottery, guild=self.guild, view=discord.ui.View()
        )

        await interaction.followup.send(view=view, ephemeral=True)


class LotteryButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Lottery",
            style=discord.ButtonStyle.success,
            custom_id="persistent_view:data_lottery_start",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = discord.ui.View()
        view.add_item(item=GenerateCoupons(label="Lottery"))
        view.add_item(item=ViewPlayerCoupons())
        await interaction.followup.send(view=view, ephemeral=True)


class GenerateCoupons(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id="persistent_view:generate_coupons_button",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = GuildObject(server_id=interaction.guild.id)

        try:
            lottery = (
                Lottery.select()
                .where(
                    Lottery.server_id == interaction.guild.id,
                    Lottery.numbers_picked.is_null(True),
                    Lottery.end_time > datetime.datetime.now(),
                )
                .order_by(Lottery.id.desc())
            )
        except DoesNotExist:
            lottery = None

        if lottery:
            lottery = lottery.get()
            # Check user balance
            balance = guild.balance(discord_user_id=interaction.user.id)
            if balance < int(lottery.price):
                message = f"""
**__Current Balance:__** {guild.to_locale(balance)}
Hold up Degen! You don't have enough {guild.token_name}!
Price is {guild.to_locale(lottery.price)} pr. ticket
"""
                # TODO Send deposit button here
                await interaction.followup.send(content=message, ephemeral=True)
                return

            if int(lottery.jackpot_bonus) > 0:
                bonus_message = (
                    f"Jackpot Bonus: **{guild.to_locale(lottery.jackpot_bonus)}**"
                )
            else:
                bonus_message = ""

            embed_1 = discord.Embed(
                title=f"{guild.token_name} Lottery",
                description=f"""
Total Prize Pool: **{guild.to_locale(int(lottery.prize_pool) + int(lottery.jackpot_bonus))}**
{bonus_message}
                """,
                color=discord.Color.red(),
            )

            embed_1.set_thumbnail(
                url="https://s4.gifyu.com/images/ticket-final-5x-lottery-small.png"
            )

            time_end = utc.localize(
                datetime.datetime.fromisoformat(str(lottery.end_time))
            )
            time_end_unix = f"<t:{int(datetime.datetime.timestamp(time_end))}:R>"

            embed_1.add_field(name="Price", value=f"`{guild.to_locale(lottery.price)}`")
            embed_1.add_field(name="Sold", value=f"`{lottery.sold}`")
            embed_1.add_field(name="Ending", value=time_end_unix)

            embed_2 = discord.Embed(
                title=f"Choose Your Ticket",
                description=f"""
Choose a randomly generated ticket. 
If youre not happy with the numbers, click refresh.

                """,
                color=discord.Color.red(),
            )

            # Generate embeds
            embeds = [embed_1, embed_2]

            view = generate_coupon_view(
                lottery=lottery, guild=guild, view=discord.ui.View()
            )

            await interaction.followup.send(embeds=embeds, view=view, ephemeral=True)
        else:
            await interaction.followup.send(
                content=f"There are no lotteries for {guild.token_name}", ephemeral=True
            )


bool_choices = [
    OptionChoice(name="Yes", value="Yes"),
    OptionChoice(name="No", value="No"),
]


class LotteryBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.persistent_views_added = False
        # self.end_lottery.start()

    @discord.slash_command()
    async def prepare_lottery(
        self,
        ctx: commands.Context,
        message_id: discord.Option(str, "Update existing embed", default=None),
    ):
        """Prepares the Lottery Embed"""

        member = ctx.guild.get_member(int(ctx.user.id))

        roles = member.roles

        some_role = get_admin_role(server_id=ctx.guild.id)

        if some_role:
            admin_role = ctx.guild.get_role(int(some_role))
        else:
            admin_role = None

        if admin_role in roles:
            view = discord.ui.View(timeout=None)
            view.add_item(item=GenerateCoupons(label=f"Buy Lottery Coupons"))
            view.add_item(item=ViewPlayerCoupons())
            embed = discord.Embed(
                title="LOTTERY",
                description=f"""
Description
                        """,
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
            await ctx.respond("You can't do that")

    @discord.slash_command()
    async def create_lottery(
        self, ctx: commands.Context, price: discord.Option(float, "Set a price")
    ):
        """Create Lottery"""
        await ctx.response.defer(ephemeral=True)

        guild = GuildObject(server_id=ctx.guild.id)

        lottery = start_new_lottery(
            server_id=ctx.guild.id,
            end_time=7,
            price=guild.from_eth(price),
            price_pool="0",
            jackpot_bonus="0",
        )

        if lottery:
            await ctx.followup.send("Lottery created", ephemeral=True)
        else:
            await ctx.followup.send(
                "There was an error creating the lottery", ephemeral=True
            )

    @discord.slash_command()
    async def send_prizetable(
        self,
        ctx: commands.Context,
        lottery_id: discord.Option(int, "Add lottery ID", default=None),
    ):
        await ctx.response.defer(ephemeral=True)
        embed = generate_prize_table(lottery_id=lottery_id, guild_id=ctx.guild.id)
        await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command()
    async def add_jackpot_bonus(
        self,
        ctx: commands.Context,
        lottery_id: discord.Option(int, "To Which Lottery?", default=None),
        amount: discord.Option(float, "How Much?", default=None),
    ):
        """Add Bonus To Jackpot"""
        await ctx.response.defer(ephemeral=True)

        if ctx.user.id == 363377402220511248:
            lottery = Lottery.get(lottery_id)

            guild = GuildObject(server_id=lottery.server_id)

            bonus = guild.from_eth(eth=amount)

            Lottery.update(jackpot_bonus=bonus).where(
                Lottery.id == lottery_id
            ).execute()

            try:
                guild.debit(
                    discord_user_id=ctx.user.id,
                    amount=bonus,
                    note=f"Bonus for lottery #{lottery_id}",
                )
            except InsufficientFunds:
                await ctx.followup.send(
                    content="You don't have enough funds", ephemeral=True
                )
                return

            await ctx.followup.send(content="Done", ephemeral=True)
        else:
            await ctx.followup.send(content="Missing permissions", ephemeral=True)

    @discord.slash_command()
    async def pick_winner(self, ctx: commands.Context):
        """Manually pick a winner"""
        await ctx.response.defer(ephemeral=True)

        if ctx.user.id == ctx.guild.admin.id:
            await end_lottery(self.bot)

            await ctx.followup.send("Done", ephemeral=True)
        else:
            await ctx.followup.send("Missing permission", ephemeral=True)

    @tasks.loop(seconds=60)
    async def auto_pick_winner(self):
        """Automatically pick a winner"""
        await end_lottery(self.bot)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:
            view = discord.ui.View(timeout=None)
            view.add_item(item=GenerateCoupons(label=f"Buy Lottery Coupons"))
            view.add_item(item=ViewPlayerCoupons())
            view.add_item(item=LotteryButton())
            # view.add_item(item=ViewPrizes())
            self.bot.add_view(view)
            self.persistent_views_added = True
        print("Lottery is ready")


def setup(bot):
    bot.add_cog(LotteryBot(bot))
