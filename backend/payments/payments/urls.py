from django.urls import path

from payments.views import (
    AvailableGatewaysView,
    ChargeTripPaymentView,
    GatewayWebhookView,
    MyDriverBalanceView,
    RefundPaymentView,
    TripPaymentView,
)


# تُضمَّن تحت api/v1/ في config/urls.py
#
# ملاحظة على الترتيب: مسار الإشعارات تحت payments/webhooks/ وليس على
# جذر api/v1/، حتى لا يزاحم رمز بوابة يومًا ما اسم مسار آخر.
urlpatterns = [
    path(
        "payments/gateways/",
        AvailableGatewaysView.as_view(),
        name="payment-gateways",
    ),
    path(
        "trips/<int:ride_id>/payment/",
        TripPaymentView.as_view(),
        name="trip-payment",
    ),
    path(
        "trips/<int:ride_id>/payment/charge/",
        ChargeTripPaymentView.as_view(),
        name="trip-payment-charge",
    ),
    path(
        "me/driver-balance/",
        MyDriverBalanceView.as_view(),
        name="my-driver-balance",
    ),
    path(
        "payments/<int:payment_id>/refund/",
        RefundPaymentView.as_view(),
        name="payment-refund",
    ),
    path(
        "payments/webhooks/<str:gateway_code>/",
        GatewayWebhookView.as_view(),
        name="payment-webhook",
    ),
]
