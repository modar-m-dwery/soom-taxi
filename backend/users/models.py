from django.contrib.gis.db import models as gis_models

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserRole(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    DRIVER = "driver", "Driver"
    ADMIN = "admin", "Admin"
    SUPPORT = "support", "Support"


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    UNDISCLOSED = "undisclosed", "Prefer not to say"


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required.")

        user = self.model(
            phone=phone,
            **extra_fields,
        )

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if not password:
            raise ValueError("Superuser must have a password.")

        return self.create_user(
            phone=phone,
            password=password,
            **extra_fields,
        )


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )

    name = models.CharField(
        max_length=150,
        blank=True,
    )

    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        default=Gender.UNDISCLOSED,
    )

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
    )

    is_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"

    REQUIRED_FIELDS = []

    def __str__(self):
        return self.phone


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )

    preferences = models.JSONField(
        default=dict,
        blank=True,
    )

    # الإحالة: «زبون يجلب زبونًا». الرمز يُولَّد مرّةً ويُشارَك، والمدعوّ
    # يُدخله قبل رحلته الأولى. المكافأة تُصرف بعد الإنجاز لا قبله.
    referral_code = models.CharField(
        max_length=8, unique=True, null=True, blank=True, db_index=True,
    )
    referred_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="referred_customers",
    )
    first_ride_discount_used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._new_referral_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _new_referral_code():
        # حروف وأرقام لا تلتبس في الكتابة اليدوية على واتساب (بلا 0/O/1/I).
        import secrets
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not CustomerProfile.objects.filter(referral_code=code).exists():
                return code
        raise RuntimeError("تعذّر توليد رمز إحالة فريد.")

    def __str__(self):
        return f"CustomerProfile({self.user.phone})"


class DriverProfile(models.Model):
    class DriverStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )

    status = models.CharField(
        max_length=20,
        choices=DriverStatus.choices,
        default=DriverStatus.PENDING,
    )

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
    )

    online = models.BooleanField(
        default=False,
    )

    current_occupancy = models.PositiveSmallIntegerField(
        default=0,
    )

    available_seats = models.PositiveSmallIntegerField(
        default=0,
    )

    last_location_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # منطقة السائق الأمّ.
    #
    # لماذا حقل ثابت وليس اشتقاقًا من الموقع الحيّ؟ لأنّ السؤالين مختلفان.
    # «أين هو الآن؟» يجيب عنه الموقع، وهو ما تستعمله المطابقة فعلًا ولا
    # يتغيّر هنا شيء. أمّا «تحت أيّ مدينة يُدار هذا السائق؟» فسؤال إداريّ
    # لا جغرافيّ: بأيّ قواعد تُقاس مهله، وفي تقارير أيّ مشغّل يظهر، ومن
    # يوثّق وثائقه. سائق جبلة الذي أنهى رحلة في اللاذقية لا يصير سائق
    # اللاذقية لأنّه هناك الآن.
    #
    # NULL يعني «لم يُحدَّد بعد» — يُملأ تلقائيًّا من أوّل اتّصال، ويبقى
    # للمشغّل حقّ تغييره.
    home_service_area = models.ForeignKey(
        "locations.ServiceArea",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drivers",
        db_index=True,
        help_text=(
            "المدينة التي يُدار هذا السائق تحت قواعدها. "
            "تُملأ تلقائيًّا عند أوّل اتّصال إن تُركت فارغة."
        ),
    )

    verification_note = models.CharField(
        max_length=500,
        blank=True,
    )

    # «السائق المؤسّس»: واحد من الثلاثين الأوائل في خطّة التسعين يومًا.
    # الوعد المكتوب والموقَّع في ورقة المؤسّس: إعفاءٌ دائم من أيّ عمولة مهما
    # كبرت المنصّة. العمولة صفر للجميع اليوم، لكن يوم تُفعَّل لمدينةٍ من
    # لوحة الإدارة يبقى صافي هذا السائق = أجرته كاملة — بلا مبرمج.
    founder_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="رقمه بين المؤسّسين (١–٣٠) كما في ورقة المؤسّس، أو فارغ.",
    )
    commission_exempt = models.BooleanField(
        default=False,
        help_text="لا تُخصم منه عمولة المنصّة أبدًا (المؤسّسون).",
    )

    verified_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_drivers",
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    current_location = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DriverProfile({self.user.phone})"

    @property
    def remaining_seats(self):
        return max(self.available_seats - self.current_occupancy, 0)


class DeviceToken(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )

    token = models.CharField(
        max_length=512,
        unique=True,
    )

    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.phone} - {self.platform}"


class OTPChallenge(models.Model):
    phone = models.CharField(
        max_length=20,
        db_index=True,
    )

    code_hash = models.CharField(
        max_length=128,
    )

    # ملح لكلّ تحدٍّ. بدونه يخدم جدولٌ واحد كلّ الصفوف: الرمز ستّ خانات،
    # ومليون بصمة تُبنى في ثوانٍ. راجع OTPService.hash_code
    code_salt = models.CharField(
        max_length=32,
        blank=True,
        default="",
    )

    attempts = models.PositiveSmallIntegerField(
        default=0,
    )

    max_attempts = models.PositiveSmallIntegerField(
        default=5,
    )

    expires_at = models.DateTimeField()

    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    device_id = models.CharField(
        max_length=255,
        blank=True,
    )

    request_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["phone", "-created_at"],
            ),
        ]

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

    @property
    def attempts_exhausted(self):
        return self.attempts >= self.max_attempts

    def __str__(self):
        return f"OTPChallenge({self.phone})"







