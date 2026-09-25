import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from users.models import OTPChallenge


class OTPService:

    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _pepper() -> bytes:
        """
        سرٌّ من الخادم يدخل في البصمة ولا يُخزَّن معها.

        الافتراضي `SECRET_KEY` — موجود دائمًا، ومنفصلٌ عن القاعدة. يمكن
        فصله بمفتاح خاصّ (`OTP_HASH_PEPPER`) لتدويره وحده دون إبطال
        الجلسات كلّها.
        """
        pepper = getattr(settings, "OTP_HASH_PEPPER", "") or settings.SECRET_KEY
        return str(pepper).encode("utf-8")

    @classmethod
    def hash_code(cls, code: str, salt: str = "") -> str:
        """
        بصمة الرمز = HMAC(pepper, salt + code).

        لماذا لا SHA-256 عارية
        ----------------------
        الرمز ستّ خانات — مليون احتمال. جدول قوس قزح لمليون سطر يُبنى في
        ثوانٍ، فأيّ قراءة لجدول `OTPChallenge` (نسخة احتياطية مسرَّبة،
        حقن SQL للقراءة، مطّلع من الداخل) تكشف كلّ رمز حيّ فورًا. وهذا
        يُفرغ شرط الوثيقة «لا يُخزَّن الرمز كنصّ صريح» من معناه: بصمةٌ
        قابلة للعكس في ثوانٍ ليست إخفاءً.

        الملح لكلّ تحدٍّ يمنع جدولًا واحدًا يخدم كلّ الصفوف، والفلفل
        يمنع بناء الجدول أصلًا لمن لا يملك سرّ الخادم.
        """
        message = f"{salt}:{code}".encode("utf-8")
        return hmac.new(cls._pepper(), message, hashlib.sha256).hexdigest()

    @classmethod
    def create_challenge(
        cls,
        phone: str,
        device_id: str = "",
        request_ip: str | None = None,
    ) -> tuple[OTPChallenge, str]:

        code = cls.generate_code()
        salt = secrets.token_hex(8)

        challenge = OTPChallenge.objects.create(
            phone=phone,
            code_salt=salt,
            code_hash=cls.hash_code(code, salt),
            max_attempts=settings.OTP_MAX_ATTEMPTS,
            expires_at=timezone.now()
            + timedelta(seconds=settings.OTP_TTL_SECONDS),
            device_id=device_id,
            request_ip=request_ip,
        )

        return challenge, code

    @classmethod
    def verify_code(
        cls,
        challenge: OTPChallenge,
        code: str,
    ) -> bool:

        if challenge.is_expired:
            return False

        if challenge.is_consumed:
            return False

        if challenge.attempts_exhausted:
            return False

        challenge.attempts += 1

        is_valid = secrets.compare_digest(
            challenge.code_hash,
            cls.hash_code(code, challenge.code_salt or ""),
        )

        if is_valid:
            challenge.consumed_at = timezone.now()

        challenge.save(
            update_fields=[
                "attempts",
                "consumed_at",
            ]
        )

        return is_valid