from accounts.models import User
from tests.accounts.helpers import ReviewTestBase


class AdminAccountListTests(ReviewTestBase):
    URL = '/api/accounts/admin/accounts/'

    def test_moderator_can_list_accounts(self):
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 4)

    def test_regular_user_cannot_list_accounts(self):
        self.client.force_authenticate(self.applicant)
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_anonymous_cannot_list_accounts(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.URL).status_code, (401, 403))

    def test_rows_include_roles_and_state_but_no_private_details(self):
        self.other.phone_number = '902-555-0100'
        self.other.postal_address = '123 Main Street'
        self.other.save()

        response = self.client.get(self.URL, {'search': 'other@test.com'})
        row = response.data['results'][0]

        self.assertIn('roles', row)
        self.assertEqual(row['account_state'], 'Active')
        self.assertNotIn('phone_number', row)
        self.assertNotIn('postal_address', row)
        self.assertNotIn('902-555-0100', response.content.decode())

    def test_roles_are_listed_per_account(self):
        response = self.client.get(self.URL, {'search': 'admin@test.com'})

        self.assertIn('Administrator', response.data['results'][0]['roles'])

    def test_search_by_email(self):
        response = self.client.get(self.URL, {'search': 'applicant'})

        emails = [row['email'] for row in response.data['results']]
        self.assertEqual(emails, ['applicant@test.com'])

    def test_search_by_display_name(self):
        self.other.display_name = 'Zebra Fan'
        self.other.save()

        response = self.client.get(self.URL, {'search': 'zebra'})

        self.assertEqual([row['id'] for row in response.data['results']], [self.other.pk])

    def test_results_are_paginated(self):
        for i in range(11):
            User.objects.create_user(f'user{i}@test.com', 'password')

        first = self.client.get(self.URL)
        second = self.client.get(self.URL, {'page': 2})

        self.assertEqual(first.data['count'], 15)
        self.assertEqual(len(first.data['results']), 10)
        self.assertEqual(len(second.data['results']), 5)

    def test_page_out_of_range_returns_404(self):
        self.assertEqual(self.client.get(self.URL, {'page': 99}).status_code, 404)
