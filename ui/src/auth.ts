// Browser side of per-user auth. graph-api's /api/health (always public) says whether auth is on.
// With AUTH_MODE=oidc we sign in with the IdP (authorization code + PKCE via oidc-client-ts), keep the
// session in sessionStorage, renew the access token silently before it expires, and hand it to api.ts
// (Authorization header) and the SSE stream (?access_token=).
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

export interface AuthInfo {
  mode: 'none' | 'oidc'
  user?: { username: string; name: string; email: string; groups: string[] }
}

let manager: UserManager | null = null
let current: User | null = null
const listeners = new Set<() => void>()

export const accessToken = (): string | null => current?.access_token ?? null
export const onTokenChange = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
const set = (u: User | null) => { current = u; listeners.forEach((fn) => fn()) }

/** Resolve once the app may render: immediately with auth off, after sign-in with auth on. */
export async function bootstrap(): Promise<AuthInfo> {
  const health = await fetch('/api/health').then((r) => r.json()).catch(() => ({}))
  const cfg = health.auth as { mode: string; issuer?: string; client_id?: string } | undefined
  if (!cfg || cfg.mode !== 'oidc') return { mode: 'none' }

  manager = new UserManager({
    authority: cfg.issuer!,
    client_id: cfg.client_id!,
    redirect_uri: `${window.location.origin}/`,
    post_logout_redirect_uri: `${window.location.origin}/`,
    response_type: 'code',
    scope: 'openid profile email',
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  })
  manager.events.addUserLoaded(set)
  manager.events.addUserUnloaded(() => set(null))
  manager.events.addSilentRenewError(() => manager?.signinRedirect())

  const params = new URLSearchParams(window.location.search)
  if (params.has('code') && params.has('state')) {
    const u = await manager.signinRedirectCallback()
    const back = (u.state as string | undefined) ?? '/'
    window.history.replaceState({}, document.title, back)
  }
  const user = await manager.getUser()
  if (!user || user.expired) {
    await manager.signinRedirect({ state: window.location.pathname + window.location.hash })
    return new Promise(() => {}) // the browser is leaving for the IdP
  }
  set(user)
  const p = (user.profile ?? {}) as Record<string, unknown>
  return {
    mode: 'oidc',
    user: {
      username: String(p.preferred_username ?? p.sub),
      name: String(p.name ?? p.preferred_username ?? ''),
      email: String(p.email ?? ''),
      groups: ((p.groups as string[] | undefined) ?? []).map((g) => g.replace(/^\//, '')),
    },
  }
}

/** Called by api.ts on a 401: the session is gone, so start a new sign-in. */
export function reauthenticate() {
  manager?.signinRedirect({ state: window.location.pathname + window.location.hash })
}

export function signOut() {
  manager?.signoutRedirect()
}
