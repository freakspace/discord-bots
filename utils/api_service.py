import requests
import os
import json

from dotenv import load_dotenv

from utils.utils import get_domain

load_dotenv()

API_KEY = os.getenv("API_KEY")

environment = os.getenv("ENVIRONMENT")

# TODO Not implemented
def get_user_nfts(discord_user_id: int) -> list:
    return [1,2,3]

    url = f"{get_domain()}//api/users/{discord_user_id}/nfts"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
        }

    response = requests.request("GET", url, headers=headers)
    
    if response.status_code == 200:
        return list(map(int, response.json()))
    else:
        return []

# TODO Not implemented
def get_user_deposit_address(server_id: int, discord_user_id: int) -> str:
    return "abcdefg"

    url = f"{get_domain()}/api/{server_id}/{discord_user_id}/get-deposit-address"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
    }

    response = requests.request("GET", url, headers=headers).json()

    if "walletAddress" in response:
        return response["walletAddress"]
    else:
        return None

# TODO Not implemented
def confirm_deposit(server_id: int, discord_user_id: int):
    return "abcdefg"
    url = f"{get_domain()}/api/{server_id}/{discord_user_id}/send-token-to-main-address"

    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
    }

    response = requests.request("GET", url, headers=headers).json()

    if "transactionId" in response:
        return response["transactionId"]
    elif "message" in response:
        raise Exception(response["message"])

# TODO Not implemented
def make_withdraw(server_id: int, discord_user_id: int, amount: int, address: str):
    return "abcdefg"

    print(f"Trying to withdraw: {amount} tokens")

    url = f"{get_domain()}/api/{server_id}/{discord_user_id}/withdrawal-token"

    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
    }

    body = json.dumps({
        "amount": amount,
        "address": address
    })

    response = requests.request("POST", url, headers=headers, data=body).json()


    if "transactionId" in response:
        return response["transactionId"]
    elif "message" in response:
        raise Exception(response["message"])

