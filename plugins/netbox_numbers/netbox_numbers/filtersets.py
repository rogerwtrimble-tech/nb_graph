import django_filters
from django.db.models import Q

from dcim.models import Interface, Site
from netbox.filtersets import PrimaryModelFilterSet
from tenancy.models import Tenant

from .choices import NumberStatusChoices
from .models import TelephoneNumber


class TelephoneNumberFilterSet(PrimaryModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=NumberStatusChoices)
    site_id = django_filters.ModelMultipleChoiceFilter(queryset=Site.objects.all())
    tenant_id = django_filters.ModelMultipleChoiceFilter(queryset=Tenant.objects.all())
    interface_id = django_filters.ModelMultipleChoiceFilter(queryset=Interface.objects.all())
    device_id = django_filters.NumberFilter(field_name='interface__device_id')
    assigned = django_filters.BooleanFilter(field_name='interface', lookup_expr='isnull', exclude=True)

    class Meta:
        model = TelephoneNumber
        fields = ('id', 'number', 'sip_username', 'description')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(number__icontains=value) | Q(sip_username__icontains=value) | Q(description__icontains=value)
        )
