from django.urls import path

from growth.views import MyIncentivesView

urlpatterns = [
    path("me/incentives/", MyIncentivesView.as_view(), name="my-incentives"),
]
