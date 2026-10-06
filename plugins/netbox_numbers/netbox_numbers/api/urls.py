from netbox.api.routers import NetBoxRouter

from .views import TelephoneNumberViewSet

app_name = 'netbox_numbers-api'

router = NetBoxRouter()
router.register('telephone-numbers', TelephoneNumberViewSet)

urlpatterns = router.urls
