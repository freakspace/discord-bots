import os
import asyncio
import locale

from dotenv import load_dotenv

import discord
from discord.ext import commands

load_dotenv()

locale.setlocale(locale.LC_ALL, 'en_US.utf8')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot_rafflestore = commands.Bot(intents=intents, auto_sync_commands=True)


cogs_list_rafflestore = [
    #"rafflestore",
    "bank"
]

for cog in cogs_list_rafflestore:
    print(f"Loading {cog}")
    bot_rafflestore.load_extension(f'cogs.{cog}')


def main():
    environment = os.getenv("ENVIRONMENT")
    print(f"Running bot in: {environment}")
    token = os.getenv("DISCORD_TOKEN")

    loop = asyncio.get_event_loop()
    loop.create_task(bot_rafflestore.start(token))

    loop.run_forever()

if __name__ == "__main__":
    main()
