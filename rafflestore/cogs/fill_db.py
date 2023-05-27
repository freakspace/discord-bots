import datetime

from utils.models import Raffle, Guild


def fill_tables():
    duration = datetime.datetime.now() + datetime.timedelta(days=7, hours=0)

    # Add a record to the Raffle table
    Raffle.create(
        server_id='1020233562454249502',
        title='Test 1',
        description='Test 1',
        image_url='https://placehold.co/300x200?text=Placeholder',
        price='100000000000000',
        duration=duration,
        winners=2,
        sold=0,
        visible=True,
        has_winner=False
    )

    # Add a record to the Guild table
    Guild.create(
        server_id='1020233562454249502',
        server_name='Client Staging',
        role_admin='1020266084844179476',
        user_access_role='1020266084844179476',
        mod_role_id='1020266084844179476',
        collector_user_id='363377402220511248',
        token_name='FUN',
        token_decimals=18,
        support_channel_id='1111448755569430620',
        notification_channel_id='1111448755569430620',
        raffle_message_id='',
        raffle_channel_id='1111448755569430620',
        raffle_winner_channel_id='1111448755569430620'
    )


if __name__ == "__main__":
    fill_tables()
