from django.urls import path

from notifications.views import (
    MyNotificationsView,
    RegisterDeviceView,
    UnregisterDeviceView,
)
from notifications.views_channels import (
    MyChannelsView,
    TelegramLinkView,
    TelegramWebhookView,
    UpdateChannelView,
)


# تُضمَّن تحت api/v1/ في config/urls.py
#
# المسارات تحت push/ عمدًا: تطبيق users قد يعرض تسجيل أجهزة على مسار آخر،
# ومسارَان متطابقان في includes مختلفة يفوز أولهما بصمت — وهو أسوأ أنواع
# التصادم لأنه لا يُبلَّغ عنه.
urlpatterns = [
    path("push/devices/register/", RegisterDeviceView.as_view(), name="push-register-device"),
    path("push/devices/unregister/", UnregisterDeviceView.as_view(), name="push-unregister-device"),
    path("me/notifications/", MyNotificationsView.as_view(), name="my-notifications"),

    # القنوات: أيّها متاح لي، وكيف أرتّبها، وكيف أربط تليغرام.
    path(
        "me/notification-channels/",
        MyChannelsView.as_view(),
        name="my-notification-channels",
    ),
    path(
        "me/notification-channels/<str:code>/",
        UpdateChannelView.as_view(),
        name="update-notification-channel",
    ),
    path(
        "notifications/channels/telegram/link/",
        TelegramLinkView.as_view(),
        name="telegram-link",
    ),
    path(
        "notifications/webhooks/telegram/",
        TelegramWebhookView.as_view(),
        name="telegram-webhook",
    ),
]
