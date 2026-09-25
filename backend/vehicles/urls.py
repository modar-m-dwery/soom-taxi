from django.urls import path

from vehicles.views import (
    ActivateVehicleView,
    DeactivateVehicleView,
    VehicleListCreateView,
)


urlpatterns = [
    path(
        "",
        VehicleListCreateView.as_view(),
        name="vehicle-list-create",
    ),

    path(
        "<int:vehicle_id>/activate/",
        ActivateVehicleView.as_view(),
        name="vehicle-activate",
    ),

    path(
        "<int:vehicle_id>/deactivate/",
        DeactivateVehicleView.as_view(),
        name="vehicle-deactivate",
    ),
]