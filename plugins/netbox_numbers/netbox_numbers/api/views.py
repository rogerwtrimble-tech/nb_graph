from netbox.api.viewsets import NetBoxModelViewSet

from ..filtersets import TelephoneNumberFilterSet
from ..models import TelephoneNumber
from .serializers import TelephoneNumberSerializer


class TelephoneNumberViewSet(NetBoxModelViewSet):
    queryset = TelephoneNumber.objects.select_related('site', 'tenant', 'interface__device')
    serializer_class = TelephoneNumberSerializer
    filterset_class = TelephoneNumberFilterSet
