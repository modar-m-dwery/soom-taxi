from django.urls import path

from maps.views import (
    RouteTestView,
)


urlpatterns = [

    path(
        "route/",
        RouteTestView.as_view(),
        name="route-test",
    ),

]