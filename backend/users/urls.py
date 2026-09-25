from django.urls import path

from users.views import (
    RequestOTPView,
    VerifyOTPView,
    BecomeDriverView,
    LogoutView,
    MeView,
    DriverProfileView,
)

# POST /api/v1/auth/request-otp/
# POST /api/v1/auth/verify-otp/
# POST /api/v1/auth/become-driver/
# POST /api/v1/auth/logout/
# GET  /api/v1/auth/me/
# GET /api/v1/auth/driver/profile/

urlpatterns = [
    path(
        "request-otp/",
        RequestOTPView.as_view(),
        name="request-otp",
    ),
    path(
        "verify-otp/",
        VerifyOTPView.as_view(),
        name="verify-otp",
    ),
    path(
        "become-driver/",
        BecomeDriverView.as_view(),
        name="become-driver",
    ),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "me/",
        MeView.as_view(),
        name="me",
    ),
    path(
        "driver/profile/",
        DriverProfileView.as_view(),
        name="driver-profile",
    ),
]