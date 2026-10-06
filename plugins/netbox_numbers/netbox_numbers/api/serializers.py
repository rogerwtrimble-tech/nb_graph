from rest_framework import serializers

from dcim.api.serializers import InterfaceSerializer, SiteSerializer
from netbox.api.fields import ChoiceField
from netbox.api.serializers import PrimaryModelSerializer
from tenancy.api.serializers import TenantSerializer

from ..choices import NumberStatusChoices
from ..models import TelephoneNumber


class TelephoneNumberSerializer(PrimaryModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_numbers-api:telephonenumber-detail')
    status = ChoiceField(choices=NumberStatusChoices, required=False)
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)
    interface = InterfaceSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = TelephoneNumber
        fields = (
            'id', 'url', 'display', 'number', 'status', 'site', 'tenant', 'interface', 'sip_username',
            'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'number', 'status', 'description')
