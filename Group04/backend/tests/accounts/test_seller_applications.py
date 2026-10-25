from datetime import timedelta
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User, SellerApplication
from security.permissions import assign_buyer
from tests.accounts.helpers import BASE, ReviewTestBase, has_role, rows


class SellerApplicationSubmissionTests(TestCase):
    def setUp(self):
        media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(media_dir.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        self.client = APIClient()
        self.user = User.objects.create_user('seller@test.com', 'password')
        self.client.force_authenticate(self.user)

    def test_csrf_endpoint_returns_token(self):
        response = self.client.get('/api/accounts/csrf/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['csrfToken'])

    def image_file(self):
        return SimpleUploadedFile(
            'identity.png',
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 16,
            content_type='image/png',
        )

    def test_person_application_is_created_pending(self):
        response = self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'person',
                'identity_document_image': self.image_file(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        application = SellerApplication.objects.get(applicant=self.user)
        self.assertEqual(application.applicant_type, SellerApplication.ApplicantType.PERSON)
        self.assertEqual(application.status, SellerApplication.Status.PENDING)
        self.assertEqual(application.company_name, '')

    def test_company_application_requires_company_fields(self):
        response = self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'company',
                'identity_document_image': self.image_file(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('company_name', response.data)
        self.assertIn('company_address', response.data)
        self.assertIn('company_tax_number', response.data)
        self.assertFalse(SellerApplication.objects.exists())

    def test_company_application_is_created(self):
        response = self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'company',
                'company_name': 'Example Ltd',
                'company_address': '123 Main Street',
                'company_tax_number': 'TAX-123',
                'identity_document_image': self.image_file(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        application = SellerApplication.objects.get(applicant=self.user)
        self.assertEqual(application.company_name, 'Example Ltd')
        self.assertEqual(application.company_address, '123 Main Street')
        self.assertEqual(application.company_tax_number, 'TAX-123')

    def test_duplicate_pending_application_is_rejected(self):
        self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'person',
                'identity_document_image': self.image_file(),
            },
            format='multipart',
        )

        response = self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'person',
                'identity_document_image': self.image_file(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(SellerApplication.objects.filter(applicant=self.user).count(), 1)

    def test_identity_document_must_be_an_image(self):
        response = self.client.post(
            '/api/accounts/seller-applications/',
            {
                'applicant_type': 'person',
                'identity_document_image': SimpleUploadedFile(
                    'document.txt',
                    b'not an image',
                    content_type='text/plain',
                ),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('identity_document_image', response.data)


class ApproveApplicationTests(ReviewTestBase):
    def test_approve_success(self):
        application = self.make_application()
        response = self.approve(application)

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.APPROVED)
        self.assertEqual(application.reviewer, self.moderator)
        self.assertIsNotNone(application.reviewed_at)

    def test_approve_grants_seller_role_and_keeps_existing_roles(self):
        assign_buyer(self.applicant)
        application = self.make_application()

        self.approve(application)

        self.assertTrue(has_role(self.applicant, 'Seller'))
        self.assertTrue(has_role(self.applicant, 'Buyer'))

    def test_approve_non_pending_is_rejected(self):
        for status in (SellerApplication.Status.APPROVED, SellerApplication.Status.REJECTED):
            application = self.make_application(status=status)
            response = self.approve(application)

            self.assertEqual(response.status_code, 409)
            application.refresh_from_db()
            self.assertEqual(application.status, status)
        self.assertFalse(has_role(self.applicant, 'Seller'))

    def test_self_approval_is_blocked(self):
        application = self.make_application(applicant=self.moderator)
        response = self.approve(application)

        self.assertEqual(response.status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.PENDING)
        self.assertFalse(has_role(self.moderator, 'Seller'))

    def test_administrator_can_approve(self):
        self.client.force_authenticate(self.admin)
        application = self.make_application()

        self.assertEqual(self.approve(application).status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.reviewer, self.admin)

    def test_administrator_cannot_approve_own_application(self):
        self.client.force_authenticate(self.admin)
        application = self.make_application(applicant=self.admin)

        self.assertEqual(self.approve(application).status_code, 403)

    def test_regular_user_cannot_approve(self):
        self.client.force_authenticate(self.applicant)
        application = self.make_application()

        self.assertEqual(self.approve(application).status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.PENDING)

    def test_unknown_application_returns_404(self):
        response = self.client.post(f'{BASE}/999999/approve/')
        self.assertEqual(response.status_code, 404)


class RejectApplicationTests(ReviewTestBase):
    def test_reject_success_records_reason_and_time(self):
        application = self.make_application()
        before = timezone.now()

        response = self.reject(application)

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.REJECTED)
        self.assertEqual(application.reviewer, self.moderator)
        self.assertEqual(application.review_reason, 'Document is unreadable.')
        self.assertGreaterEqual(application.reviewed_at, before)
        self.assertFalse(has_role(self.applicant, 'Seller'))

    def test_reject_requires_a_reason(self):
        application = self.make_application()

        self.assertEqual(self.reject(application, reason='   ').status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.PENDING)

    def test_reject_non_pending_is_rejected(self):
        application = self.make_application(status=SellerApplication.Status.APPROVED)

        self.assertEqual(self.reject(application).status_code, 409)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.APPROVED)

    def test_self_rejection_is_blocked(self):
        application = self.make_application(applicant=self.moderator)

        self.assertEqual(self.reject(application).status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.PENDING)

    def test_administrator_can_reject(self):
        self.client.force_authenticate(self.admin)
        application = self.make_application()

        self.assertEqual(self.reject(application).status_code, 200)

    def test_regular_user_cannot_reject(self):
        self.client.force_authenticate(self.applicant)
        application = self.make_application()

        self.assertEqual(self.reject(application).status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, SellerApplication.Status.PENDING)


class ReviewQueueTests(ReviewTestBase):
    def test_queue_lists_only_pending_applications(self):
        pending = self.make_application()
        self.make_application(applicant=self.other, status=SellerApplication.Status.APPROVED)
        rejected_user = User.objects.create_user('rejected@test.com', 'password')
        self.make_application(applicant=rejected_user, status=SellerApplication.Status.REJECTED)

        response = self.client.get(f'{BASE}/pending/')

        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in rows(response)]
        self.assertEqual(ids, [pending.pk])

    def test_queue_includes_applicant_email(self):
        self.make_application()
        response = self.client.get(f'{BASE}/pending/')

        self.assertEqual(rows(response)[0]['applicant_email'], 'applicant@test.com')

    def test_administrator_can_view_queue(self):
        self.client.force_authenticate(self.admin)
        self.make_application()

        response = self.client.get(f'{BASE}/pending/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows(response)), 1)

    def test_regular_user_cannot_view_queue(self):
        self.client.force_authenticate(self.applicant)
        self.assertEqual(self.client.get(f'{BASE}/pending/').status_code, 403)

    def test_anonymous_cannot_view_queue(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f'{BASE}/pending/').status_code, (401, 403))

    def test_approved_application_leaves_the_queue(self):
        application = self.make_application()
        self.approve(application)

        response = self.client.get(f'{BASE}/pending/')
        self.assertEqual(rows(response), [])


class MyApplicationsTests(ReviewTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.applicant)

    def test_shows_only_my_applications(self):
        mine = self.make_application()
        self.make_application(applicant=self.other)

        response = self.client.get(f'{BASE}/mine/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in rows(response)], [mine.pk])

    def test_shows_pending_approved_and_rejected(self):
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=300)
        self.make_application(status=SellerApplication.Status.APPROVED, hours_since_review=100)
        self.make_application(status=SellerApplication.Status.PENDING)

        response = self.client.get(f'{BASE}/mine/')

        statuses = sorted(row['status'] for row in rows(response))
        self.assertEqual(statuses, ['approved', 'pending', 'rejected'])

    def test_rejected_application_includes_reason(self):
        application = self.make_application()
        self.client.force_authenticate(self.moderator)
        self.reject(application, reason='Name does not match document.')

        self.client.force_authenticate(self.applicant)
        response = self.client.get(f'{BASE}/mine/')

        self.assertEqual(rows(response)[0]['review_reason'], 'Name does not match document.')

    def test_newest_application_is_first(self):
        old = self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=300)
        new = self.make_application(status=SellerApplication.Status.PENDING)
        SellerApplication.objects.filter(pk=old.pk).update(created_at=new.created_at - timedelta(seconds=1))

        response = self.client.get(f'{BASE}/mine/')

        self.assertEqual([row['id'] for row in rows(response)], [new.pk, old.pk])

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f'{BASE}/mine/').status_code, (401, 403))

    def test_approved_applicant_sees_approved_application(self):
        application = self.make_application()
        self.client.force_authenticate(self.moderator)
        self.approve(application)

        self.client.force_authenticate(self.applicant)
        response = self.client.get(f'{BASE}/mine/')

        self.assertEqual(rows(response)[0]['status'], 'approved')


class ReapplyEligibilityTests(ReviewTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.applicant)

    def test_can_apply_with_no_history(self):
        self.assertEqual(self.apply().status_code, 201)

    def test_cannot_reapply_within_168_hours(self):
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=167)

        response = self.apply()

        self.assertEqual(response.status_code, 403)
        self.assertIn('available_at', response.data)
        self.assertEqual(SellerApplication.objects.filter(applicant=self.applicant).count(), 1)

    def test_can_reapply_after_168_hours(self):
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=169)

        self.assertEqual(self.apply().status_code, 201)

    def test_cooldown_is_measured_from_the_latest_rejection(self):
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=500)
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=1)

        self.assertEqual(self.apply().status_code, 403)

    def test_cooldown_only_applies_to_the_rejected_user(self):
        self.make_application(status=SellerApplication.Status.REJECTED, hours_since_review=1)

        self.client.force_authenticate(self.other)
        self.assertEqual(self.apply().status_code, 201)

    def test_reapply_available_at_is_168_hours_after_rejection(self):
        application = self.make_application(
            status=SellerApplication.Status.REJECTED, hours_since_review=10
        )

        available_at = SellerApplication.reapply_available_at(self.applicant)

        self.assertEqual(available_at, application.reviewed_at + timedelta(hours=168))

    def test_reapply_available_at_is_none_without_rejection(self):
        self.make_application(status=SellerApplication.Status.APPROVED, hours_since_review=5)
        self.assertIsNone(SellerApplication.reapply_available_at(self.applicant))

    def test_mine_includes_reapply_time_for_rejected_only(self):
        rejected = self.make_application(
            status=SellerApplication.Status.REJECTED, hours_since_review=2
        )
        approved = self.make_application(
            status=SellerApplication.Status.APPROVED, hours_since_review=400
        )

        response = self.client.get(f'{BASE}/mine/')
        by_id = {row['id']: row for row in rows(response)}

        self.assertIsNotNone(by_id[rejected.pk]['reapply_available_at'])
        self.assertIsNone(by_id[approved.pk]['reapply_available_at'])

    def test_rejection_by_moderator_starts_the_cooldown(self):
        application = self.make_application()
        self.client.force_authenticate(self.moderator)
        self.reject(application)

        self.client.force_authenticate(self.applicant)
        self.assertEqual(self.apply().status_code, 403)
