# Discord Bots

This project includes a plethora of different Discord Bots, which work together to create an immensive user experience.

- The banking bot allows users to manage their balance and earn currencies.
- The rafflestore bot makes it possible to buy raffletickets and win prizes
- The lottery will draw 5 numbers and selects winners
- The coinflip allows players to flip agains the house

The bots has previously been live in 10+ servers with more than 50k members.
The bots was connected with the Solana blockchain using different API calls.

## Installation

1. Clone the repository

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create tables:

```bash
python create_db.py
```

4. (Optional) fill tables with data:

```bash
python fill_db.py
```

## Configuration

1. Create `.env` in the root and add variables `"ENVIRONMENT"`, `"DISCORD_TOKEN"`, `"API_KEY"` and the following:

For local development:

`"DATABASE_LOCAL"`

`"USER_LOCAL"`

`"PASSWORD_LOCAL"`

`"HOST_LOCAL"`

`"PORT_LOCAL"`

For stage devnet:

`"DATABASE_STAGE_DEVNET"`

`"USER_STAGE_DEVNET"`

`"PASSWORD_STAGE_DEVNET"`

`"HOST_STAGE_DEVNET"`

`"PORT_STAGE_DEVNET"`

For stage mainnet

`"DATABASE_STAGE_MAINNET"`

`"USER_STAGE_MAINNET"`

`"PASSWORD_STAGE_MAINNET"`

`"HOST_STAGE_MAINNET"`

`"PORT_STAGE_MAINNET"`

For production

`"DATABASE_PROD"`

`"USER_PROD"`

`"PASSWORD_PROD"`

`"HOST_PROD"`

`"PORT_PROD"`

ENVIRONMENT can be either one of: local, prod, stage-devnet, stage-mainnet to easily switch between databases.

## Usage

To start the bot use

```bash
python run.py
```
