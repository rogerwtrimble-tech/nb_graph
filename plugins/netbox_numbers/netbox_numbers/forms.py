from django import forms

from dcim.models import Device, Interface, Site
from netbox.forms import NetBoxModelFilterSetForm, PrimaryModelForm
from tenancy.models import Tenant
from utilities.forms import add_blank_choice
from utilities.forms.fields import CommentField, DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.rendering import FieldSet

from .choices import NumberStatusChoices
from .models import TelephoneNumber


class TelephoneNumberForm(PrimaryModelForm):
    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(), required=False, initial_params={'interfaces': '$interface'}
    )
    interface = DynamicModelChoiceField(
        queryset=Interface.objects.all(), required=False, query_params={'device_id': '$device'}
    )
    comments = CommentField()

    fieldsets = (
        FieldSet('number', 'status', 'site', 'tenant', 'sip_username', 'description', 'tags', name='Number'),
        FieldSet('device', 'interface', name='Assignment'),
    )

    class Meta:
        model = TelephoneNumber
        fields = (
            'number', 'status', 'site', 'tenant', 'interface', 'sip_username', 'description', 'comments', 'tags',
        )


class TelephoneNumberFilterForm(NetBoxModelFilterSetForm):
    model = TelephoneNumber
    status = forms.MultipleChoiceField(choices=NumberStatusChoices, required=False)
    site_id = DynamicModelMultipleChoiceField(queryset=Site.objects.all(), required=False, label='Site')
    tenant_id = DynamicModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False, label='Tenant')
    assigned = forms.NullBooleanField(
        required=False, widget=forms.Select(choices=add_blank_choice([(True, 'Yes'), (False, 'No')]))
    )
