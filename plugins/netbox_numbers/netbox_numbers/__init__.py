from netbox.plugins import PluginConfig


class NetBoxNumbersConfig(PluginConfig):
    name = 'netbox_numbers'
    verbose_name = 'Numbers'
    description = 'Telephone number (DID) inventory, assignable to interfaces'
    version = '0.1.0'
    author = 'nb_graph'
    base_url = 'numbers'
    min_version = '4.7.0'
    max_version = '4.99'


config = NetBoxNumbersConfig
