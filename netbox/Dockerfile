# NetBox image for nb_graph = the official netbox-docker image + the netbox_numbers plugin.
# Build context is the repository root (see docker-compose.yml).
ARG NETBOX_IMAGE=docker.io/netboxcommunity/netbox:v4.7-5.1.1
FROM ${NETBOX_IMAGE}

COPY plugins/netbox_numbers /opt/nb_plugins/netbox_numbers
RUN /usr/local/bin/uv pip install --no-cache /opt/nb_plugins/netbox_numbers

COPY netbox/configuration/ /etc/netbox/config/
RUN DEBUG="true" SECRET_KEY="dummyKeyWithMinimumLength-------------------------" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
