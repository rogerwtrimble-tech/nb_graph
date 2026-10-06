# NetBox configuration

`configuration.py`, `extra.py` and `logging.py` are copied unchanged from
[netbox-community/netbox-docker](https://github.com/netbox-community/netbox-docker) 5.1.1 (Apache-2.0, see
`LICENSE.netbox-docker`). They read every setting from environment variables, which come from
`netbox/env/netbox.env` and the root `.env` (see `docker-compose.yml`).

`plugins.py` is ours: it turns on the `netbox_numbers` plugin.

The whole folder is mounted read-only into the NetBox containers at `/etc/netbox/config`.
