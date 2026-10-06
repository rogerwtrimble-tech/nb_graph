import django_tables2 as tables

from netbox.tables import NetBoxTable, columns

from .models import TelephoneNumber


class TelephoneNumberTable(NetBoxTable):
    number = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()
    site = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    device = tables.Column(accessor='interface__device', linkify=True, verbose_name='Device')
    interface = tables.Column(linkify=True)
    tags = columns.TagColumn(url_name='plugins:netbox_numbers:telephonenumber_list')

    class Meta(NetBoxTable.Meta):
        model = TelephoneNumber
        fields = (
            'pk', 'id', 'number', 'status', 'site', 'tenant', 'device', 'interface', 'sip_username',
            'description', 'tags', 'created', 'last_updated',
        )
        default_columns = ('number', 'status', 'site', 'tenant', 'device', 'interface', 'description')
