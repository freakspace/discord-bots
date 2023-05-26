import requests
import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")

environment = os.getenv("ENVIRONMENT")


def get_user_nfts(discord_user_id: int) -> list:

    url = f""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
        }

    response = requests.request("GET", url, headers=headers)
    
    if response.status_code == 200:
        return list(map(int, response.json()))
    else:
        return []


