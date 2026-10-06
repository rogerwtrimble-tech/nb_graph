from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, tables
from .models import TelephoneNumber


@register_model_view(TelephoneNumber, 'list', path='', detail=False)
class TelephoneNumberListView(generic.ObjectListView):
    queryset = TelephoneNumber.objects.select_related('site', 'tenant', 'interface__device')
    filterset = filtersets.TelephoneNumberFilterSet
    filterset_form = forms.TelephoneNumberFilterForm
    table = tables.TelephoneNumberTable


@register_model_view(TelephoneNumber)
class TelephoneNumberView(generic.ObjectView):
    queryset = TelephoneNumber.objects.all()
    template_name = 'netbox_numbers/telephonenumber.html'


@register_model_view(TelephoneNumber, 'add', detail=False)
@register_model_view(TelephoneNumber, 'edit')
class TelephoneNumberEditView(generic.ObjectEditView):
    queryset = TelephoneNumber.objects.all()
    form = forms.TelephoneNumberForm


@register_model_view(TelephoneNumber, 'delete')
class TelephoneNumberDeleteView(generic.ObjectDeleteView):
    queryset = TelephoneNumber.objects.all()


@register_model_view(TelephoneNumber, 'bulk_delete', path='delete', detail=False)
class TelephoneNumberBulkDeleteView(generic.BulkDeleteView):
    queryset = TelephoneNumber.objects.all()
    filterset = filtersets.TelephoneNumberFilterSet
    table = tables.TelephoneNumberTable
