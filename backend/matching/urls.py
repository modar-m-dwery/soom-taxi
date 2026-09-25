from django.urls import path

from matching.views import (
    DriverRideCandidatesView,
    DriverSubmitOfferView,
    CustomerRideOffersView,
    CustomerSelectOfferView,

    SharedJoinAcceptView,
    SharedAvailableOffersView,

    CustomerScheduledSharedTripsView,
    CustomerJoinScheduledSharedTripView,

    DriverPublishTripView,
    PublishedTripsCatalogView,
    CustomerBookPublishedTripView,

    RideNearbyVehiclesView,
    RideInvitationCreateView,
    DriverInvitationListView,
    DriverInvitationAcceptView,
    DriverInvitationRejectView,
)


urlpatterns = [

    path(
        "driver/rides/candidates/",
        DriverRideCandidatesView.as_view(),
        name="driver-ride-candidates",
    ),

    path(
        "driver/rides/<int:ride_id>/offers/",
        DriverSubmitOfferView.as_view(),
        name="driver-submit-offer",
    ),

    path(
        "customer/rides/<int:ride_id>/offers/",
        CustomerRideOffersView.as_view(),
        name="customer-ride-offers",
    ),

    path(
        "customer/rides/"
        "<int:ride_id>/offers/"
        "<int:offer_id>/select/",
        CustomerSelectOfferView.as_view(),
        name="customer-select-offer",
    ),

    # ----------------------------
    # Instant Shared
    # ----------------------------

    path(
        "customer/rides/"
        "<int:ride_id>/shared-offers/",
        SharedAvailableOffersView.as_view(),
        name="shared-available-offers",
    ),

    path(
        "customer/shared-offers/"
        "<int:join_request_id>/accept/",
        SharedJoinAcceptView.as_view(),
        name="shared-join-accept",
    ),

    # ----------------------------
    # Scheduled Shared (city)
    # ----------------------------

    path(
        "customer/rides/"
        "<int:ride_id>/scheduled-shared-trips/",
        CustomerScheduledSharedTripsView.as_view(),
        name="scheduled-shared-trips",
    ),

    path(
        "customer/rides/"
        "<int:ride_id>/scheduled-shared-trips/"
        "<int:trip_id>/join/",
        CustomerJoinScheduledSharedTripView.as_view(),
        name="scheduled-shared-trip-join",
    ),

    # ----------------------------
    # سفريات / سرفيس / رحلات ترفيهية
    # ----------------------------

    path(
        "driver/trips/publish/",
        DriverPublishTripView.as_view(),
        name="driver-publish-trip",
    ),

    path(
        "trips/",
        PublishedTripsCatalogView.as_view(),
        name="published-trips-catalog",
    ),

    path(
        "trips/<int:trip_id>/book/",
        CustomerBookPublishedTripView.as_view(),
        name="published-trip-book",
    ),

        # ----------------------------
    # الخريطة الحيّة والدعوة المباشرة
    # ----------------------------

    path(
        "customer/rides/<int:ride_id>/nearby-vehicles/",
        RideNearbyVehiclesView.as_view(),
        name="ride-nearby-vehicles",
    ),

    path(
        "customer/rides/<int:ride_id>/invitations/",
        RideInvitationCreateView.as_view(),
        name="ride-invitation-create",
    ),

    path(
        "driver/invitations/",
        DriverInvitationListView.as_view(),
        name="driver-invitations",
    ),

    path(
        "driver/invitations/<int:invitation_id>/accept/",
        DriverInvitationAcceptView.as_view(),
        name="driver-invitation-accept",
    ),

    path(
        "driver/invitations/<int:invitation_id>/reject/",
        DriverInvitationRejectView.as_view(),
        name="driver-invitation-reject",
    ),

]