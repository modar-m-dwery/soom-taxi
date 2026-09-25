from rest_framework.permissions import BasePermission

from users.models import UserRole


class IsCustomer(BasePermission):
    message = "Customer access required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.CUSTOMER
        )


class IsDriver(BasePermission):
    message = "Driver access required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.DRIVER
        )


class IsAdmin(BasePermission):
    """
    إداريّ: الدور `admin` **أو** `is_staff`.

    لماذا الاثنان
    -------------
    كان في المشروع ثلاثة تعريفات متضاربة لكلمة «إداري»:

      • `IsAdmin` القديم    → الدور وحده، تستعمله نقاط توثيق السائقين
      • `IsAdminUser` (DRF) → `is_staff` وحده، تستعمله لوحة التشغيل والاسترجاع
      • `AdminLiveConsumer` → الدور أو `is_staff`، وهو الأوسع

    والنتيجة كانت باب خلفيّ صامت: حسابٌ بدور `support` بلا `is_staff`
    يُمنع من `GET /ops/drivers/live/` ثمّ يفتح نفس البيانات — إحداثيات
    دقيقة وأرقام هواتف — بثًّا حيًّا على `/ws/admin/live/`. صلاحيةٌ
    تُمنع في مكان وتُمنح في آخر ليست صلاحية.

    تعريفٌ واحد يُستعمل في كلّ مكان: هنا.
    """

    message = "Admin access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.role == UserRole.ADMIN or user.is_staff)
        )


class IsStaffOrSupport(BasePermission):
    """
    قراءة تشغيلية: إداريّ أو دعم.

    الدعم يقرأ ولا يتدخّل. التدخّل (`ops` الكتابية) يبقى على `IsAdmin`.
    """

    message = "Operations access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or user.role in (UserRole.ADMIN, UserRole.SUPPORT)
            )
        )


class IsSupport(BasePermission):
    message = "Support access required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.SUPPORT
        )