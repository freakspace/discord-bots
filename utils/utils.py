import os

import discord

from utils.models import Guild, DoesNotExist

environment = os.getenv("ENVIRONMENT")

def get_admin_role(server_id: int):
    try:
        role_id = Guild.get(Guild.server_id == server_id).role_admin
        if role_id:
            return int(role_id)
        else:
            return None
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_access_role(server_id: int):
    try:
        role_id = Guild.get(Guild.server_id == server_id).user_access_role
        if role_id:
            return int(role_id)
        else:
            return None
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_mod_role(server_id: int):
    try:
        role_id = Guild.get(Guild.server_id == server_id).mod_role_id
        if role_id:
            return int(role_id)
        else:
            return None
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_support_channel(server_id: int):
    try:
        channel_id = Guild.get(Guild.server_id == server_id).support_channel_id
        return channel_id
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_notification_channel(server_id: int):
    try:
        channel_id = Guild.get(
            Guild.server_id == server_id).notification_channel_id
        return channel_id
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_raffle_channel(server_id: int):
    try:
        channel_id = Guild.get(Guild.server_id == server_id).raffle_channel_id
        return channel_id
    except DoesNotExist:
        return None
    except ValueError:
        return None


def get_raffle_winner_channel(server_id: int):
    try:
        channel_id = Guild.get(
            Guild.server_id == server_id).raffle_winner_channel_id
        return channel_id
    except DoesNotExist:
        return None
    except ValueError:
        return None


def generate_option(title: str, value: str, description: str):
    option = discord.SelectOption(
        label=title,
        value=value,
        description=description
    )
    return option

async def send_notification_message(bot_or_client: object, message: str, channel_id: str):
    """Sends a message to any channel by id"""
    channel = bot_or_client.get_channel(int(channel_id))
    if channel != None:
        await channel.send(message)
    else:
        print("Can´t find channel")
        return
    

def get_domain():

    domain = {
        "local": "https://staging-devnet.degenlabz.com",
        "stage-devnet": "https://staging-devnet.degenlabz.com",
        "stage-mainnet": "https://staging-mainnet.degenlabz.com",
        "prod": "https://degenz-verfication-git-master-degen-labz.vercel.app/"
    }

    return domain[environment]