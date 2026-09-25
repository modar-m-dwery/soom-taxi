from django.urls import re_path

from realtime.consumers import (
    AdminLiveConsumer,
    DriverConnectionConsumer,
    CustomerConnectionConsumer,
    RideConsumer,
    DriverRoomConsumer,
    MarketplaceConsumer,
)

websocket_urlpatterns = [
    # جزء D: مسارات اختبار اتصال فقط - أبقيناها لأنها ما زالت مفيدة لتشخيص
    # مشاكل auth/reconnect بمعزل عن أي منطق أعمال.
    re_path(
        r"^ws/connection-test/driver/(?P<driver_id>\d+)/$",
        DriverConnectionConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/connection-test/customer/(?P<ride_id>\d+)/$",
        CustomerConnectionConsumer.as_asgi(),
    ),

    # جزء E: Ride Room الحقيقية
    re_path(
        r"^ws/rides/(?P<ride_id>\d+)/$",
        RideConsumer.as_asgi(),
    ),

    # جزء F: Driver Room الحقيقية (presence + location)
    re_path(
        r"^ws/driver/(?P<driver_id>\d+)/$",
        DriverRoomConsumer.as_asgi(),
    ),

    # لوحة التشغيل الحيّة (§7 في الوثيقة). is_staff فقط — تبثّ إحداثيات
    # دقيقة وأرقام هواتف، وهي ما تخفيه الخريطة العامّة عن الزبائن.
    re_path(
        r"^ws/admin/live/$",
        AdminLiveConsumer.as_asgi(),
    ),

    # جزء G: Marketplace Rooms (خلايا geohash - راجع تطبيق locations)
    re_path(
        r"^ws/marketplace/(?P<area_id>[A-Za-z0-9:_-]+)/$",
        MarketplaceConsumer.as_asgi(),
    ),
]