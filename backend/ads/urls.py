from django.urls import path

from ads.views import AdEventView, AdImageView, AdsListView

urlpatterns = [
    path("ads/", AdsListView.as_view(), name="ads-list"),
    path("ads/<int:ad_id>/event/", AdEventView.as_view(), name="ads-event"),
    path("ads/<int:ad_id>/image/", AdImageView.as_view(), name="ads-image"),
]
