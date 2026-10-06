#!/usr/bin/env python3
"""Create .env from .env.example with fresh random secrets (python3 only, works on macOS/Linux/Windows)."""
import pathlib
import secrets
import string
import sys

root = pathlib.Path(__file__).resolve().parent.parent
src, dst = root / '.env.example', root / '.env'
if dst.exists() and '--force' not in sys.argv:
    sys.exit('.env already exists (use --force to overwrite)')

alnum = string.ascii_letters + string.digits
rand = lambda n, chars=alnum: ''.join(secrets.choice(chars) for _ in range(n))  # noqa: E731
values = {
    'DB_PASSWORD': rand(24), 'REDIS_PASSWORD': rand(24), 'REDIS_CACHE_PASSWORD': rand(24),
    'SECRET_KEY': rand(60), 'API_TOKEN_PEPPER_1': rand(60), 'SUPERUSER_PASSWORD': rand(16),
    'SUPERUSER_API_KEY': rand(12), 'SUPERUSER_API_TOKEN': rand(40), 'WEBHOOK_SECRET': rand(32),
}
out = []
for line in src.read_text().splitlines():
    key = line.split('=', 1)[0]
    out.append(f'{key}={values[key]}' if key in values and not line.startswith('#') else line)
dst.write_text('\n'.join(out) + '\n')
print(f'wrote {dst}\n  NetBox login: admin / {values["SUPERUSER_PASSWORD"]}')
