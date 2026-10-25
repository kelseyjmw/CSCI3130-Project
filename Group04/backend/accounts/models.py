import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    # This will be used to normalize email adresses, as requested by the project's requirements.
    @classmethod
    def normalize_email(cls, email):
        return (email or '').strip().lower()

    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: self.normalize_email(username)})

    async def aget_by_natural_key(self, username):
        return await self.aget(**{self.model.USERNAME_FIELD: self.normalize_email(username)})

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)


# Custom user model that uses email as the unique identifier instead of username.
class User(AbstractUser):
    username = None

    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    session_version = models.IntegerField(default=0)
    display_name = models.CharField(max_length=50, blank=True)
    phone_number = models.CharField(max_length=25, blank=True)
    postal_address = models.CharField(max_length=300, blank=True)
    account_state = models.CharField(max_length=20, default="Active")
    suspension_reason = models.TextField(blank=True)
    state_changed_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def public_display_name(self):
        # Never fall back to the email address, since profiles are public.
        return self.display_name or f"Member {self.pk}"

    def save(self, **kwargs):
        self.email = self.__class__.objects.normalize_email(self.email)
        super().save(**kwargs)


class EmailVerification(models.Model):
    TTL = timedelta(hours=24)

    class Purpose(models.TextChoices):
        REGISTRATION = 'registration', 'Registration'
        EMAIL_CHANGE = 'email_change', 'Email change'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verifications')
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    new_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, user, purpose, new_email=''):
        cls.objects.filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
            invalidated_at__isnull=True,
        ).update(invalidated_at=timezone.now())

        raw_token = secrets.token_urlsafe(18)
        verification = cls.objects.create(
            user=user,
            purpose=purpose,
            new_email=new_email,
            token_hash=cls.hash_token(raw_token),
            expires_at=timezone.now() + cls.TTL,
        )
        return verification, raw_token

    @classmethod
    def resolve(cls, raw_token, purpose):
        return cls.objects.filter(token_hash=cls.hash_token(raw_token), purpose=purpose).first()

    @property
    def is_valid(self):
        return (
            self.used_at is None
            and self.invalidated_at is None
            and timezone.now() < self.expires_at
        )

    def consume(self):
        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])


class LoginHistory(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="login_history"
    )

    login_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.login_time}"


# Bulk updates and deletes skip AuditLog.save() and AuditLog.delete(), so they are blocked here as well.
class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied("Audit records cannot be changed.")

    def delete(self):
        raise PermissionDenied("Audit records cannot be deleted.")


# Written through log.audit_logger.Logger. Records can be added, but never changed or deleted.
class AuditLog(models.Model):
    # Account ids instead of foreign keys, so a record stays the same after its accounts are deleted.
    actor = models.BigIntegerField(
        null=True,
        blank=True
    )

    target = models.BigIntegerField(
        null=True,
        blank=True
    )

    action = models.CharField(max_length=50)

    result = models.CharField(max_length=20)

    reason = models.TextField(blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]

    def save(self, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("Audit records cannot be changed.")
        super().save(**kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit records cannot be deleted.")

    def __str__(self):
        return f"{self.timestamp} - {self.action} - {self.result}"


class PasswordResetToken(models.Model):
    TTL = timedelta(minutes=30)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens"
    )

    token_hash = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)

    used_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, user):
        cls.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        raw_token = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            token_hash=cls.hash_token(raw_token),
        )
        return token, raw_token

    @classmethod
    def resolve(cls, raw_token):
        return cls.objects.filter(token_hash=cls.hash_token(raw_token)).first()

    @property
    def is_valid(self):
        return (
            self.used_at is None
            and timezone.now() < self.created_at + self.TTL
        )

class SellerApplication(models.Model):
    class ApplicantType(models.TextChoices):
        PERSON = "person", "Person"
        COMPANY = "company", "Company"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    applicant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="seller_applications",
    )
    applicant_type = models.CharField(
        max_length=10,
        choices=ApplicantType.choices,
    )
    company_name = models.CharField(max_length=255, blank=True)
    company_address = models.TextField(blank=True)
    company_tax_number = models.CharField(max_length=100, blank=True)
    identity_document_image = models.FileField(
        upload_to="seller_applications/identity_documents/",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="reviewed_seller_applications",
        null=True,
        blank=True,
    )
    review_reason = models.TextField(blank=True)

    REAPPLY_COOLDOWN = timedelta(hours=168)

    @classmethod
    def reapply_available_at(cls, user):
        last_rejection = (
            cls.objects
            .filter(applicant=user, status=cls.Status.REJECTED, reviewed_at__isnull=False)
            .order_by('-reviewed_at')
            .first()
        )
        return last_rejection.reviewed_at + cls.REAPPLY_COOLDOWN if last_rejection else None

    class Meta:
        db_table = "seller_applications"
        constraints = [
            models.UniqueConstraint(
                fields=["applicant"],
                condition=models.Q(status="pending"),
                name="one_pending_seller_application_per_applicant",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(applicant_type="company")
                    | (
                        ~models.Q(company_name="")
                        & ~models.Q(company_address="")
                        & ~models.Q(company_tax_number="")
                    )
                ),
                name="company_seller_application_requires_company_details",
            ),
        ]
