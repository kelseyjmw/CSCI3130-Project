from unittest.mock import patch

from django.core import mail
from django.test import override_settings

from catalog.models import AuctionNotification, AuctionOrder
from catalog.services import refresh_listing_state
from tests.catalog.auction_helpers import AuctionTestCase


@override_settings(MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
class AuctionNotificationTests(AuctionTestCase):
    def test_sale_emails_seller_and_winner_once_after_commit(self):
        self.bid('25')
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.finish()
            self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 2)
        self.assertEqual({message.to[0] for message in mail.outbox}, {self.seller.email, self.buyer.email})
        for message in mail.outbox:
            self.assertIn(self.listing.title, message.body)
            self.assertIn('CAD 25.00', message.body)
            self.assertIn('Pending', message.body)
        with self.captureOnCommitCallbacks(execute=True) as repeated:
            refresh_listing_state(self.listing.pk)
        self.assertEqual(repeated, [])
        self.assertEqual(len(mail.outbox), 2)

    def test_without_winner_seller_gets_email_and_visible_notification_without_order(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.finish()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.seller.email])
        self.assertIn('No eligible winner', mail.outbox[0].body)
        self.client.force_authenticate(self.seller)
        response = self.client.get('/api/catalog/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['listing_id'], self.listing.pk)
        self.assertIsNone(response.data[0]['order_id'])
        self.assertEqual(AuctionOrder.objects.count(), 0)

    def test_email_failure_keeps_sale_and_notifications_and_still_emails_other_recipient(self):
        self.bid('25')
        with patch('catalog.emails.send_auction_end_notification', side_effect=OSError('SMTP unavailable')):
            with self.assertLogs(level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    self.finish()
        self.assertEqual(AuctionOrder.objects.count(), 1)
        self.assertEqual(AuctionNotification.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.buyer.email])
