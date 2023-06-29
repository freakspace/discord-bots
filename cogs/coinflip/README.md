# Coinflip

This Discord bot served as a RaffleStore in a Discord server with more than 10,000 members.
It can work independetly from the bankingbot, however they go very well together.
If you implement blockchain API calls in the bankingbot, it will allow you to sell raffletickets for crypto tokens of any kind.

## Features

- Admin can create raffles directly from Discord
- Players can buy raffletickets in quantities of 1, 10 and 100
- Players can see their stash, and how many they bought of each raffle
- Raffles can be picked manually or automatically.
- The code will pick a winner using random.choices

## Commands

- /prepare_raffle
- /add_raffle
- /remove_raffle

## Task

- hide_raffles
- pick_winners

## Installation

1. Include 'rafflestore' in the cogs list in /run.py

## Usage

To show the rafflestore embed, run the command /prepare_raffle
If you want to update an existing embed, pass the message id as argument when you run the command
