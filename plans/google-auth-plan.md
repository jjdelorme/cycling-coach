# Google Authentication & RBAC Implementation Plan

## Overview

Add Google Sign-In to the React frontend, verify tokens in the FastAPI backend, and enforce per-user role-based access control (read / readwrite / none) across all API routes — including the AI coaching agent's tool calls.

## Architecture

```
React App                         FastAPI Backend
  │                                    │
  ├─ @react-oauth/google ──→ Google ID Token (JWT, ~1hr TTL)
  │   (silent refresh on expiry)       │
  │                                    │
  ├─ Every API call ──→ Authorization: Bearer <id_token>
  │                                    │
  │                          google.oauth2.id_token.verify_oauth2_token()
  │                          ↓
  │                          Lookup email → role in `users` table
  │                          ↓
  │                          Enforce role on route (Depends)
  │                          ↓
  │                          403 if insufficient permissions
```

**Token refresh:** Use `@react-oauth/google`'s built-in silent refresh (option a). Google's library handles re-authentication before the ~1hr token expiry via a hidden iframe. No custom JWT or token exchange needed.

**Default role:** `none` — new Google users who sign in get no access until an admin explicitly grants read or readwrite.

---

## Decisions Summary

| Decision | Choice |
|----------|--------|
| Token refresh | Silent re-auth via Google library (option a) |
| Default new user role | `none` (explicit allowlist) |
| Admin UI | Simple user management page (add by Gmail, set role) |
| Coaching agent | `read` role required, but respects per-user permissions — read tools work for `read` users, `write` tools return 403 if user doesn't have write |
| Config location | Environment variables alongside `DATABASE_URL` in `server/config.py` |

---

## Implementation Steps

### Step 1: GCP OAuth Client ID Setup (Manual)

1. Go to GCP Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID, type "Web application"
3. Add authorized JavaScript origins:
   - `http://localhost:5173` (Vite dev)
   - `http://localhost:8000` (FastAPI serving built frontend)
   - Production Cloud Run URL when ready
4. Note the **Client ID** (no client secret needed for frontend-only ID token flow)

### Step 2: Backend Config (`server/config.py`)

Add two new environment variables to the existing config pattern:

```python
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_AUTH_ENABLED = os.getenv("GOOGLE_AUTH_ENABLED", "true").lower() == "true"
```

- `GOOGLE_CLIENT_ID` — the OAuth client ID from Step 1
- `GOOGLE_AUTH_ENABLED` — kill switch for local dev without auth (`false` to disable)

These will be secrets/env vars on Cloud Run alongside `DATABASE_URL`.

### Step 3: Database — `users` Table

Add to both `_SCHEMA_SQLITE` and `_SCHEMA_POSTGRES` in `server/database.py`:

**SQLite:**
```sql
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMP DEFAULT (datetime('now')),
    last_login TIMESTAMP
);
```

**Postgres:**
```sql
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

**Seed data:** On first run or via a script, insert admin user:
```sql
INSERT OR IGNORE INTO users (email, role) VALUES ('your-email@gmail.com', 'admin');
```

### Step 4: Backend Auth Module (`server/auth.py`)

New module with:

1. **`verify_google_token(token: str) -> dict`**
   - Uses `google.oauth2.id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)`
   - Returns token claims (email, name, picture, etc.)
   - Raises 401 on invalid/expired token

2. **`CurrentUser` dataclass/model:**
   ```python
   class CurrentUser:
       email: str
       display_name: str
       avatar_url: str
       role: str  # 'none', 'read', 'readwrite', 'admin'
   ```

3. **`get_current_user(request: Request) -> CurrentUser`** — FastAPI dependency:
   - Extract `Authorization: Bearer <token>` header
   - Verify token → get email
   - Lookup user in DB → get role (default `none` if not in table)
   - Upsert user record (update `last_login`, `display_name`, `avatar_url` from Google claims)
   - If `GOOGLE_AUTH_ENABLED` is `false`, return a dev-mode user with `admin` role
   - Return `CurrentUser`

4. **Permission dependencies:**
   ```python
   def require_read(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
       if user.role not in ('read', 'readwrite', 'admin'):
           raise HTTPException(403, "Read access required")
       return user

   def require_write(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
       if user.role not in ('readwrite', 'admin'):
           raise HTTPException(403, "Write access required")
       return user

   def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
       if user.role != 'admin':
           raise HTTPException(403, "Admin access required")
       return user
   ```

### Step 5: Backend — Protect All Routes

Apply `Depends()` to every router. Categorization:

| Router | GET endpoints | Mutating endpoints |
|--------|--------------|-------------------|
| `/api/rides` | `require_read` | `require_write` (PUT comments, title) |
| `/api/pmc` | `require_read` | — |
| `/api/analysis` | `require_read` | — |
| `/api/plan` | `require_read` | `require_write` (POST generate, sync; PUT notes) |
| `/api/coaching` | `require_read` (sessions, settings GET) | `require_write` (chat, PUT settings, DELETE session, POST reset) |
| `/api/sync` | `require_read` | `require_write` (POST start, backfill) |
| `/api/athlete` | `require_read` | `require_write` (PUT settings) |
| `/api/health` | No auth (public health check) | — |

**New admin router** (`/api/admin`):
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/admin/users` | List all users with roles |
| POST | `/api/admin/users` | Add user by email + role |
| PUT | `/api/admin/users/{email}` | Update user role |
| DELETE | `/api/admin/users/{email}` | Remove user |
| GET | `/api/users/me` | Get current user info (any authenticated user) |

All admin routes use `require_admin`.

### Step 6: Coaching Agent — Permission-Aware Tool Calls

This is the key architectural piece. The coaching agent must respect the caller's permissions.

**Approach:** Pass the `CurrentUser` into the `chat()` function. Wrap write tools with a permission check.

1. **Modify `chat()` signature** in `server/coaching/agent.py`:
   ```python
   async def chat(message: str, session_id: str, user: CurrentUser) -> AsyncGenerator:
   ```

2. **Wrap write tools with permission gate:**
   Create a decorator or wrapper that checks the user's role before executing any write tool. If the user has `read` but not `readwrite`, the tool returns an error message like:
   ```
   "You don't have write permissions. Ask an administrator to upgrade your access."
   ```
   This way the agent receives the error as a tool response and can relay it conversationally to the user.

3. **Read tools remain accessible** to users with `read` role — the agent can still answer questions, show data, analyze rides, etc.

4. **Route-level:** The `POST /api/coaching/chat` endpoint requires `require_read` (not `require_write`) so read-only users can chat. The write restriction happens at the tool level inside the agent.

### Step 7: Frontend — Auth Context & Provider

**New files:**
- `frontend/src/lib/auth.tsx` — Auth context, provider, hook

**Dependencies:**
```bash
npm install @react-oauth/google
```

**AuthProvider:**
```tsx
// Wraps app in GoogleOAuthProvider
// Manages: user state, token, login/logout
// On login: sends token to backend /api/users/me to get role
// Token stored in React state (not localStorage)
// Silent refresh via Google's library (onNonceCallback / auto re-auth)
```

**AuthContext exposes:**
```typescript
interface AuthContext {
  user: { email: string; name: string; avatar: string; role: string } | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
}
```

### Step 8: Frontend — API Interceptor

**Modify `frontend/src/lib/api.ts`:**

- Add auth token to every `fetch()` call via the existing wrapper:
  ```typescript
  headers: {
    'Authorization': `Bearer ${getToken()}`,
    'Content-Type': 'application/json',
  }
  ```
- Handle 401 → redirect to login
- Handle 403 → show "insufficient permissions" toast/message

### Step 9: Frontend — Header/Toolbar Redesign

**Current layout** (right side of header):
```
[Theme Toggle] [Coach Button]
```

**New layout** (right side of header):
```
[Tabs...]                    [Coach Icon] [Settings Gear] [Avatar]
```

Changes to `Layout.tsx`:

1. **Remove the text "Coach" button** — replace with a toolbar icon (chat bubble icon, e.g., from Heroicons or inline SVG)
2. **Move Settings out of the tab bar** — replace with a gear icon in the toolbar area
3. **Add gear icon** — clicking navigates to Settings tab
4. **Add avatar component** — circular Google profile photo in upper right
   - Click opens a dropdown: user email, role badge, theme toggle, "Sign Out"
   - When not logged in: shows "Sign In" button with Google logo
5. **Mobile bottom nav** — keep existing tabs minus Settings; add gear icon to bottom bar or keep Coach + Settings in toolbar area

**Avatar dropdown detail:**
```
┌─────────────────────┐
│ [photo] Jason Del   │
│ jason@gmail.com     │
│ Role: Admin         │
├─────────────────────┤
│ ☀ Theme: Dark    ▾ │
│ Sign Out            │
└─────────────────────┘
```

### Step 10: Frontend — Admin UI (Settings Sub-page)

Add a "Users" section to the existing Settings page (only visible to admin role):

```
┌─ User Management ──────────────────────────────┐
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │ Email              │ Role         │      │   │
│  │ jason@gmail.com    │ Admin        │      │   │
│  │ friend@gmail.com   │ Read         │ [✕]  │   │
│  │ coach@gmail.com    │ Read/Write   │ [✕]  │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  Add user: [email input] [role dropdown] [Add]  │
│                                                  │
└──────────────────────────────────────────────────┘
```

- Role dropdown: Read, Read/Write (no "none" — just delete the user)
- Cannot change own role or delete self (prevent lockout)
- Real-time table, no pagination needed (small user count)

### Step 11: Frontend — Login Page / Unauthenticated State

- If not authenticated: show a centered login page with Google Sign-In button and app branding
- If authenticated but role is `none`: show a "Waiting for access" message explaining they need an admin to grant access
- If authenticated with `read` or `readwrite`: show normal app

### Step 12: CORS Update

In `server/main.py`, tighten CORS from `allow_origins=["*"]` to specific origins:
```python
allow_origins=[
    "http://localhost:5173",
    "http://localhost:8000",
    os.getenv("CORS_ALLOWED_ORIGIN", ""),  # Production Cloud Run URL
]
```

---

## File Change Summary

### New Files
| File | Purpose |
|------|---------|
| `server/auth.py` | Token verification, CurrentUser, permission dependencies |
| `server/routers/admin.py` | User management API routes |
| `frontend/src/lib/auth.tsx` | Auth context, provider, useAuth hook |
| `frontend/src/components/UserAvatar.tsx` | Avatar dropdown component |
| `frontend/src/components/UserManagement.tsx` | Admin user management UI |
| `frontend/src/components/LoginPage.tsx` | Login / waiting-for-access screens |

### Modified Files
| File | Changes |
|------|---------|
| `server/config.py` | Add `GOOGLE_CLIENT_ID`, `GOOGLE_AUTH_ENABLED` |
| `server/database.py` | Add `users` table to both schemas |
| `server/main.py` | Include admin router, tighten CORS, add `/api/users/me` |
| `server/routers/rides.py` | Add `Depends(require_read/write)` to all routes |
| `server/routers/pmc.py` | Add `Depends(require_read)` |
| `server/routers/analysis.py` | Add `Depends(require_read)` |
| `server/routers/plan.py` | Add `Depends(require_read/write)` |
| `server/routers/coaching.py` | Add `Depends(require_read)`, pass user to `chat()` |
| `server/routers/sync.py` | Add `Depends(require_read/write)` |
| `server/routers/athlete.py` | Add `Depends(require_read/write)` |
| `server/coaching/agent.py` | Accept `CurrentUser`, wrap write tools with permission gate |
| `server/coaching/planning_tools.py` | (Possibly) add permission check wrapper |
| `frontend/src/App.tsx` | Wrap in `AuthProvider`, add login gate |
| `frontend/src/components/Layout.tsx` | Redesign header toolbar |
| `frontend/src/components/CoachPanel.tsx` | Handle 403 from agent gracefully |
| `frontend/src/lib/api.ts` | Add auth header interceptor, 401/403 handling |
| `frontend/src/pages/SettingsPage.tsx` | Add UserManagement section for admins |
| `requirements.txt` | Add `google-auth` if not already present |
| `frontend/package.json` | Add `@react-oauth/google` |

---

## Implementation Order

1. **GCP Console** — Create OAuth Client ID (manual, ~5 min)
2. **Backend first** — `server/config.py` → `database.py` → `auth.py` → `admin.py` router → protect all routes
3. **Coaching agent** — Permission-aware tool wrapping
4. **Frontend auth** — `auth.tsx` context → `api.ts` interceptor → `LoginPage.tsx`
5. **Frontend UI** — Header redesign → `UserAvatar.tsx` → `UserManagement.tsx`
6. **CORS** — Tighten origins
7. **Test** — End-to-end flow: login → role check → read/write enforcement → agent permission gating

---

## Open Questions / Future Considerations

- **Multi-athlete:** Currently all data is single-user. Auth identifies *who is accessing*, not *whose data*. Multi-athlete would be a separate, larger effort requiring user_id FKs on most tables.
- **Service account for agent:** The coaching agent currently runs server-side. Its tool calls don't go through HTTP, so permission checks need to be injected at the Python function level, not via HTTP middleware.
- **Rate limiting:** Not in scope, but worth considering for the coaching chat endpoint once exposed to multiple users.
- **Refresh token edge case:** If the Google silent refresh fails (e.g., user revoked access), the frontend should catch the 401 and redirect to login.
