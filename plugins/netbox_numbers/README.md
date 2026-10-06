# netbox-numbers

A small NetBox 4.7 plugin, part of **nb_graph**, that keeps an inventory of telephone numbers (DIDs).

The community phone-number plugins (`netbox-phonebox`, `phonebox_plugin`) only support NetBox up to 4.4, so this repo ships its own minimal version.

| Field | Notes |
|---|---|
| `number` | E.164 string, unique (`+13125550100`) |
| `status` | `available` · `reserved` · `assigned` · `porting` · `deprecated` |
| `site` | The site whose number pool the number belongs to |
| `tenant` | Optional subscriber or tenant |
| `interface` | The `dcim.Interface` the number is assigned to (usually an ONT `voip` port) |
| `sip_username` | Free text |
| `description`, `comments`, `tags`, custom fields | Standard NetBox fields |

* UI: **Plugins → Numbers → Telephone Numbers**
* REST: `/api/plugins/numbers/telephone-numbers/`. Filter with `?status=available&site_id=1`, `?interface_id=42` or `?q=+1312`.
