# Bank

This Discord bot served as a bank in a Discord server with more than 10,000 members.
It was integrated with third party API's, which allowed it to make calls to the blockchain.
However the project is not active anymore, so I've decided to make the code public.
With the right developer this bot can serve as a payment gateway for any blockchain.

## Features

- Players can set a pin to open their bank account
- Withdraw tokens to a walletaddress
- Deposit tokens from the discord wallet address
- Transaction log

## Commands

- Balance
- Transfer

## Installation

1. Include 'bank' in the cogs list in /run.py
2. Implement API endpoints (to make blockchain calls) in utils/api_service.py

## Usage

To show the banking embed, run the command /prepare_bank
If you want to update an existing embed, pass the message id as argument when you run /prepare_bank
