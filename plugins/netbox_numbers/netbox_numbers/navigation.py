from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link='plugins:netbox_numbers:telephonenumber_list',
        link_text='Telephone Numbers',
        permissions=['netbox_numbers.view_telephonenumber'],
        buttons=(
            PluginMenuButton(
                'plugins:netbox_numbers:telephonenumber_add', 'Add', 'mdi mdi-plus-thick',
                permissions=['netbox_numbers.add_telephonenumber'],
            ),
        ),
    ),
)
