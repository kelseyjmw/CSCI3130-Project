from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from accounts.models import Wallet, WalletTransaction

User = get_user_model()


class WalletModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@test.com",
            password="StrongPassword123!"
        )

    def test_wallet_initial_balance_is_zero(self):
        wallet = Wallet.objects.create(user=self.user, currency="CAD")
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.currency, "CAD")

    def test_negative_balance_violates_constraint(self):
        wallet = Wallet.objects.create(user=self.user, currency="CAD")
        wallet.balance = Decimal("-10.00")
        with self.assertRaises(Exception):
            wallet.save()


class WalletTopUpValidationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="buyer@test.com",
            password="StrongPassword123!"
        )
        self.client.force_authenticate(user=self.user)
        self.wallet = Wallet.objects.create(user=self.user, currency="CAD")
        self.topup_url = reverse("wallet-topup")

    def test_valid_topup_succeeds(self):
        payload = {
            "amount": "50.00",
            "card_number": "1234567812345678",
            "cvv": "007",
            "expiry": "12/2026"
        }
        response = self.client.post(self.topup_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("50.00"))

        # Verify transaction history
        self.assertEqual(self.wallet.transactions.count(), 1)
        tx = self.wallet.transactions.first()
        self.assertEqual(tx.amount, Decimal("50.00"))
        self.assertEqual(tx.resulting_balance, Decimal("50.00"))
        self.assertEqual(tx.transaction_type, WalletTransaction.TransactionType.TOP_UP)

    def test_amount_must_be_positive(self):
        for bad_amount in ["0.00", "-15.00"]:
            payload = {
                "amount": bad_amount,
                "card_number": "1234567812345678",
                "cvv": "123",
                "expiry": "12/2026"
            }
            response = self.client.post(self.topup_url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_amount_max_two_decimal_places(self):
        payload = {
            "amount": "15.999",
            "card_number": "1234567812345678",
            "cvv": "123",
            "expiry": "12/2026"
        }
        response = self.client.post(self.topup_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_card_number_must_be_exactly_16_digits(self):
        for bad_card in ["123456781234567", "12345678123456789", "abcd567812345678"]:
            payload = {
                "amount": "20.00",
                "card_number": bad_card,
                "cvv": "123",
                "expiry": "12/2026"
            }
            response = self.client.post(self.topup_url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cvv_must_be_exactly_three_digits_with_leading_zeros(self):
        # Passes with leading zero: '007'
        valid_payload = {
            "amount": "10.00",
            "card_number": "1234567812345678",
            "cvv": "007",
            "expiry": "12/2026"
        }
        response = self.client.post(self.topup_url, valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Fails with fewer or more digits
        for bad_cvv in ["07", "1234", "abc"]:
            payload = {
                "amount": "10.00",
                "card_number": "1234567812345678",
                "cvv": bad_cvv,
                "expiry": "12/2026"
            }
            response = self.client.post(self.topup_url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expiry_boundary_november_2026(self):
        # November 2026 is current month -> MUST FAIL
        fail_payload = {
            "amount": "10.00",
            "card_number": "1234567812345678",
            "cvv": "123",
            "expiry": "11/2026"
        }
        response = self.client.post(self.topup_url, fail_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # December 2026 is after current month -> MUST PASS
        pass_payload = {
            "amount": "10.00",
            "card_number": "1234567812345678",
            "cvv": "123",
            "expiry": "12/2026"
        }
        response = self.client.post(self.topup_url, pass_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class GuestWalletAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.create_url = reverse("wallet-create")
        self.detail_url = reverse("wallet-detail")
        self.topup_url = reverse("wallet-topup")

    def test_guest_wallet_lifecycle(self):
        # 1. Guest initializes wallet currency
        create_res = self.client.post(self.create_url, {"currency": "USD"}, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(create_res.data["is_guest"])
        self.assertEqual(create_res.data["currency"], "USD")

        # 2. Cannot change currency once created
        second_create = self.client.post(self.create_url, {"currency": "CAD"}, format="json")
        self.assertEqual(second_create.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Guest top-up
        topup_res = self.client.post(self.topup_url, {
            "amount": "40.00",
            "card_number": "9876543298765432",
            "cvv": "999",
            "expiry": "01/2027"
        }, format="json")
        self.assertEqual(topup_res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(topup_res.data["balance"])), Decimal("40.00"))

        # 4. Detail view warns guest about browser session
        detail_res = self.client.get(self.detail_url)
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertIn("warning", detail_res.data)