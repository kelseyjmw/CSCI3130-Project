from django.core.mail import send_mail


def send_verification_link(email, link):
    send_mail(
        'Verify your email address',
        'Open this link within 24 hours to verify your email address:\n\n'
        f'{link}\n\n'
        'If you did not create this account, you can ignore this message.',
        None,
        [email],
    )


def send_email_change_link(new_email, link):
    send_mail(
        'Confirm your new email address',
        'Open this link within 24 hours to confirm this address for your account:\n\n'
        f'{link}\n\n'
        'Your current address stays active until this one is confirmed.',
        None,
        [new_email],
    )


def send_email_change_notice(old_email, new_email):
    send_mail(
        'Your email address was changed',
        f'The email address for your account was changed to {new_email}.\n\n'
        'If you did not make this change, contact support immediately.',
        None,
        [old_email],
    )


def send_password_reset_link(email, link):
    send_mail(
        'Reset your password',
        'Open this link within 30 minutes to reset your password:\n\n'
        f'{link}\n\n'
        'If you did not request a password reset, you can ignore this message.',
        None,
        [email],
    )


def send_password_change_notice(email):
    send_mail(
        'Your password was changed',
        'Your account password was changed successfully.\n\n'
        'If you did not make this change, contact support immediately.',
        None,
        [email],
    )
