from django.core.mail import send_mail


def send_auction_end_notification(email, auction):
    order = getattr(auction, 'order', None)
    outcome = (
        f'Winning price: {order.currency} {order.amount:.2f}. Order #{order.pk}, payment Pending.'
        if order else 'No eligible winner or order was created.'
    )
    send_mail(
        'Your auction has ended',
        f'Your auction has ended: {auction.listing.title}.\n\n{outcome}\n\n'
        'Open Notifications in the application to view the result.',
        None,
        [email],
    )

def send_auction_winner_notification(email, auction):
    order = auction.order
    send_mail(
        'You won an auction',
        f'You won the auction for {auction.listing.title}.\n\n'
        f'Winning price: {order.currency} {order.amount:.2f}. Order #{order.pk}, payment Pending.\n\n'
        'You are expected to purchase at your winning bid amount. '
        'Open Notifications in the application to view the result.',
        None,
        [email],
    )
