from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from django.core.validators import RegexValidator
from datetime import timezone as dt_timezone

from .models import SellerApplication, User, LoginHistory, AuditLog


class UserSerializer(serializers.ModelSerializer):
    previous_login = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'email_verified',
            'date_joined',
            'previous_login',
            'roles',
            'display_name',
            'phone_number',
            'postal_address',
            'account_state',
            'suspension_reason',
            'state_changed_at',
            'suspended_at',
        ]
        read_only_fields = [
            'id',
            'email',
            'email_verified',
            'date_joined',       
            'display_name',
            'phone_number',
            'postal_address',
            'account_state',
            'suspension_reason',
            'state_changed_at',
            'suspended_at',
        ]

    def get_roles(self, user):
        return list(user.roles.values_list('name', flat=True))

    def get_previous_login(self, user):
        logins = LoginHistory.objects.filter(user=user).order_by("-login_time")

        if len(logins) > 1:
            return logins[1].login_time

        return None


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'email_verified', 'password']
        read_only_fields = ['id', 'email_verified']

    def validate_email(self, value):
        value = User.objects.normalize_email(value)
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email address already exists.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class ChangeEmailSerializer(serializers.Serializer):
    new_email = serializers.EmailField()

    def validate_new_email(self, value):
        value = User.objects.normalize_email(value)
        if value == self.context['request'].user.email:
            raise serializers.ValidationError('This is already your email address.')
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                'This email address is already associated with another account.'
            )
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class NewPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        validate_password(value, self.context.get('user'))
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, self.context['request'].user)
        return value

    
class SellerApplicationSerializer(serializers.ModelSerializer):
    identity_document_image = serializers.FileField()

    class Meta:
        model = SellerApplication
        fields = [
            'applicant_type',
            'company_name',
            'company_address',
            'company_tax_number',
            'identity_document_image',
        ]

    def validate_identity_document_image(self, uploaded_file):
        file_start = uploaded_file.read(8)
        uploaded_file.seek(0)
        if not (
            file_start.startswith(b'\xff\xd8\xff')
            or file_start == b'\x89PNG\r\n\x1a\n'
        ):
            raise serializers.ValidationError('Upload a valid JPEG or PNG image.')
        return uploaded_file

    def validate(self, attrs):
        if attrs['applicant_type'] == SellerApplication.ApplicantType.COMPANY:
            required_company_fields = (
                'company_name',
                'company_address',
                'company_tax_number',
            )
            missing_fields = [
                field for field in required_company_fields if not attrs.get(field, '').strip()
            ]
            if missing_fields:
                raise serializers.ValidationError({
                    field: 'This field is required for company applications.'
                    for field in missing_fields
                })
        else:
            attrs['company_name'] = ''
            attrs['company_address'] = ''
            attrs['company_tax_number'] = ''
        return attrs

    def create(self, validated_data):
        return SellerApplication.objects.create(
            applicant=self.context['request'].user,
            **validated_data,
        )

class PendingSellerApplicationSerializer(serializers.ModelSerializer):
    applicant_email = serializers.EmailField(source='applicant.email', read_only=True)

    class Meta:
        model = SellerApplication
        fields = [
            'id', 'applicant_email', 'applicant_type', 'company_name', 'company_address',
            'company_tax_number', 'identity_document_image', 'status', 'created_at',
        ]

class MySellerApplicationSerializer(serializers.ModelSerializer):
    reapply_available_at = serializers.SerializerMethodField()

    class Meta:
        model = SellerApplication
        fields = [
            'id', 'applicant_type', 'company_name', 'status',
            'created_at', 'reviewed_at', 'review_reason', 'reapply_available_at',
        ]

    def get_reapply_available_at(self, obj):
        if obj.status != SellerApplication.Status.REJECTED or obj.reviewed_at is None:
            return None
        return obj.reviewed_at + SellerApplication.REAPPLY_COOLDOWN


class PublicProfileSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='public_display_name', read_only=True)
    member_since = serializers.DateTimeField(source='date_joined', read_only=True)
    rating = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'display_name', 'member_since', 'rating']

    def get_rating(self, obj):
        # TODO: Replace with the real average once the reviews requirements land.
        # None means "No ratings yet".
        return None


class ProfileUpdateSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(max_length=50)

    class Meta:
        model = User
        fields = ['display_name']


class AccountUpdateSerializer(serializers.ModelSerializer):
    # Private account details only.
    phone_number = serializers.CharField(
        max_length=25,
        required=False,
        allow_blank=True,
        validators=[RegexValidator(r'^[0-9+()\-\s.]{7,25}$', 'Enter a valid phone number.')],
    )
    postal_address = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = ['phone_number', 'postal_address']

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Provide at least one field to update.')
        return attrs

class AdminPanelAccountListSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'display_name', 'email_verified', 'date_joined',
            'roles', 'account_state', 'suspension_reason',
        ]

    def get_roles(self, user):
        return [role.name for role in user.roles.all()]


class AuditLogSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(default_timezone=dt_timezone.utc, read_only=True)
    class Meta:
        model = AuditLog
        fields = ['id', 'timestamp', 'actor', 'target', 'action', 'result', 'reason']
        read_only_fields = fields