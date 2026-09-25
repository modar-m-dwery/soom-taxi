from django.urls import path

from rides.views import (
    RideRequestCreateView,
    CustomerCancelRideView,
    MyRidesView,
    MyRideSubscriptionsView,
    CancelRideSubscriptionView,
)


urlpatterns = [

    path(
        "",
        RideRequestCreateView.as_view(),
        name="ride-request-create",
    ),

    # سجلّ الطلبات. يُضمَّن تحت api/v1/rides/ فيصير المسار
    # /api/v1/rides/mine/ — ولم نستخدم "" لأن الجذر محجوز لـPOST.
    path(
        "mine/",
        MyRidesView.as_view(),
        name="my-rides",
    ),

    path(
        "subscriptions/",
        MyRideSubscriptionsView.as_view(),
        name="ride-subscriptions",
    ),
    path(
        "subscriptions/<int:subscription_id>/",
        CancelRideSubscriptionView.as_view(),
        name="ride-subscription-cancel",
    ),
    path(
        "<int:ride_id>/cancel/",
        CustomerCancelRideView.as_view(),
        name="ride-cancel",
    ),

]