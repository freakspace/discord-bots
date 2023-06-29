# Discord Lottery Bot

This Discord lottery bot is completely autonomous, and can be integrated to blockchains using the banking bot.
Users can buy lottery tickets using their discord currency (from the banking bot).
Each lottery ticket has 5 numbers, the more correct numbers a user has, the higher the prize.
It works in such a way that the prize pool is split equally in to four buckets: 2 correct, 3 correct, 4 correct and 5 correct.
Naturally there will be less winners in the higher buckets, resulting in a higher prize.
All unclaimed rewards will automatically go towards the next lottery.
The bot is autonomous, so it will automatically pick winners every week, and create a new lottery immediately afterwards.

## Features

- Buy lottery tickets
- View lottery tickets
- Claim prizes
- Create lotttery
- End lottery
- Add a jackpot bonus

## Commands

- /prepare_lottery (generated the lottery embed)
- /create_lottery
- /send_prizetable
- /add_jackpot_bonus
- /end_lottery

## Installation

1. Include 'lottery' in the cogs list in /run.py
2. Run the command /prepare_lottery
3. Run the command /create_lottery

## Usage

To show the banking embed, run the command /prepare_lottery
To start a lottery run the command /create_lottery
Since the bot is autonomous, and automatically starts and ends lotteries, its only nessesary to run the /create_lottery command once
