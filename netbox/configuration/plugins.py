# nb_graph: NetBox plugins baked into the nb_graph/netbox image (see netbox/Dockerfile).
# netbox_numbers - telephone number (DID) inventory, assignable to interfaces (plugins/netbox_numbers)
PLUGINS = ['netbox_numbers']

PLUGINS_CONFIG = {
    'netbox_numbers': {},
}
