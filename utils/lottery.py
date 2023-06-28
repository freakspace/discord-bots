import random
from utils.models import Lottery, LotteryNumber
import json

# TODO Make sure lottery is ended, no more tickets to be sold
# TODO Loop through all lottery tickets
# TODO Check and save amount of correct numbers
# TODO Compute the different prize pools depending on amount of correct numbers
# TODO Loop through each lottery ticket and save the prize amount


def get_lottery_numbers():

    numbers = [n for n in range(1, 29)]

    random.shuffle(numbers)

    numbers_chosen = []

    for _ in range(5):

        numbers_chosen.append(numbers.pop())

    return numbers_chosen


def prize_table_template():
    table = {
        2: {
            "winners": 0,
            "prize": 0,
            "share": 0.15,
            "total": 0,
            "bonus": 0
        },
        3: {
            "winners": 0,
            "prize": 0,
            "share": 0.15,
            "total": 0,
            "bonus": 0
        },
        4: {
            "winners": 0,
            "prize": 0,
            "share": 0.30,
            "total": 0,
            "bonus": 0
        },
        5: {
            "winners": 0,
            "prize": 0,
            "share": 0.40,
            "total": 0,
            "bonus": 0
        }
    }

    total = 0

    for n in table:
        total += table[n]["share"]

    if total != 1.0:
        raise Exception("Total share should be 1.0")
    else:
        return table


def find_correct_numbers(lottery_id: int):
    """Loops through all lottery tickets and updates amount of correct numbers"""
    lottery_winning_numbers = Lottery.get(id=lottery_id).get_numbers()

    lottery_tickets = LotteryNumber.select().where(
        LotteryNumber.lottery_id == lottery_id)

    for ticket in lottery_tickets:

        numbers = ticket.get_numbers()

        # Get count of matching numbers
        matching_numbers = len(
            list(set(lottery_winning_numbers) & set(numbers)))

        # Update each lottery ticket with correct amount of numbers
        query = (LotteryNumber
                 .update(numbers_correct=matching_numbers)
                 .where(LotteryNumber.id == ticket.id))
        query.execute()


def calculate_prize_pool(lottery_id: int):
    """ Calculates total winner count and prize for each bucket """

    lottery = Lottery.get(id=lottery_id)
    prize_pool = lottery.prize_pool
    jackpot_bonus = lottery.jackpot_bonus

    prize_table = prize_table_template()

    lottery_tickets = LotteryNumber.select().where(
        LotteryNumber.lottery_id == lottery_id)

    # Calculate how many winners for each prize pool
    for ticket in lottery_tickets:
        if ticket.numbers_correct > 1:
            prize_table[ticket.numbers_correct]["winners"] += 1

    # Calculate the prize bucket
    for prize_bucket in prize_table:
        total = round(int(prize_pool) * prize_table[prize_bucket]["share"])

        prize_table[prize_bucket]["total"] = total

        winner_count = prize_table[prize_bucket]["winners"]

        if winner_count > 0:
            # TODO Find a better implementation than round.

            if prize_bucket == 5:
                prize_table[prize_bucket]["bonus"] = int(jackpot_bonus)
                prize = round((total + int(jackpot_bonus)) / winner_count)
            else:
                prize = round(total / winner_count)

            prize_table[prize_bucket]["prize"] = prize

    return prize_table


def pick_winning_numbers(lottery_id: int):
    numbers = get_lottery_numbers()

    lottery_tickets = LotteryNumber.select().where(
        LotteryNumber.lottery_id == lottery_id)

    numbers_list = [number.get_numbers() for number in lottery_tickets]

    while numbers in numbers_list:
        numbers = get_lottery_numbers()

    Lottery.update(numbers_picked=json.dumps(numbers)).where(
        Lottery.id == lottery_id).execute()
        
    return numbers


def calculate_prize_table(lottery: object):
    # Only calculate prize table if it doesnt exist already
    if lottery.prize_table == None:

        # Calculate prize table
        prize_table = calculate_prize_pool(
            lottery_id=lottery.id)

        # Update prize table in db
        Lottery.update(prize_table=json.dumps(prize_table)).where(
            Lottery.id == lottery.id).execute()
    else:
        prize_table = json.loads(lottery.prize_table)

    return prize_table


def computes_prizes(lottery_id: int, prize_table: dict):
    # Get all lottery tickets from lottery
    lottery_numbers = LotteryNumber.select().where(
        LotteryNumber.lottery_id == lottery_id)

    # Loop through each number and save prize
    for number in lottery_numbers:
        if number.numbers_correct > 1:
            prize = prize_table[number.numbers_correct]["prize"]
        else:
            prize = "0"
        LotteryNumber.update(prize=prize).where(
            LotteryNumber.id == number.id).execute()


