import { useState, useEffect } from 'react'
import { fetchUsers, createUser, updateUserRole, deleteUser, type UserRecord } from '../lib/api'
import { useAuth } from '../lib/auth'

const ROLE_OPTIONS = [
  { value: 'read', label: 'Read' },
  { value: 'readwrite', label: 'Read/Write' },
  { value: 'admin', label: 'Admin' },
]

export default function UserManagement() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [newEmail, setNewEmail] = useState('')
  const [newRole, setNewRole] = useState('read')
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const data = await fetchUsers()
      setUsers(data)
    } catch {
      setError('Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAdd = async () => {
    if (!newEmail.trim()) return
    setError('')
    try {
      await createUser(newEmail.trim(), newRole)
      setNewEmail('')
      setNewRole('read')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add user')
    }
  }

  const handleRoleChange = async (email: string, role: string) => {
    setError('')
    try {
      await updateUserRole(email, role)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update role')
    }
  }

  const handleDelete = async (email: string) => {
    setError('')
    try {
      await deleteUser(email)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete user')
    }
  }

  if (loading) {
    return <div className="text-text-muted text-sm">Loading users...</div>
  }

  return (
    <section>
      <h3 className="text-xl font-semibold text-text mb-1">User Management</h3>
      <p className="text-text-muted text-sm mb-4">
        Manage who can access the app and their permissions.
      </p>

      {error && (
        <div className="text-red-400 text-sm mb-3">{error}</div>
      )}

      <div className="bg-surface rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-4 py-2 text-text-muted font-medium">Email</th>
              <th className="text-left px-4 py-2 text-text-muted font-medium">Role</th>
              <th className="text-left px-4 py-2 text-text-muted font-medium">Last Login</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.email === currentUser?.email
              return (
                <tr key={u.email} className="border-b border-border last:border-0">
                  <td className="px-4 py-2 text-text">
                    <div className="flex items-center gap-2">
                      {u.avatar_url ? (
                        <img src={u.avatar_url} className="w-6 h-6 rounded-full" alt="" />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-surface2 flex items-center justify-center text-xs text-text-muted">
                          {(u.display_name || u.email).charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div>{u.display_name || u.email}</div>
                        {u.display_name && (
                          <div className="text-text-muted text-xs">{u.email}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    {isSelf ? (
                      <span className="text-accent text-sm">{u.role}</span>
                    ) : (
                      <select
                        value={u.role}
                        onChange={(e) => handleRoleChange(u.email, e.target.value)}
                        className="bg-surface2 text-text border border-border rounded px-2 py-1 text-sm"
                      >
                        {ROLE_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-2 text-text-muted text-xs">
                    {u.last_login ? new Date(u.last_login).toLocaleDateString() : 'Never'}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {!isSelf && (
                      <button
                        onClick={() => handleDelete(u.email)}
                        className="text-red-400 hover:text-red-300 text-sm"
                        title="Remove user"
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Add user form */}
        <div className="border-t border-border p-4 flex items-center gap-3">
          <input
            type="email"
            placeholder="email@gmail.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            className="flex-1 bg-surface2 text-text border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="bg-surface2 text-text border border-border rounded px-3 py-2 text-sm"
          >
            {ROLE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            onClick={handleAdd}
            className="px-4 py-2 bg-accent text-white rounded text-sm font-medium hover:opacity-90"
          >
            Add
          </button>
        </div>
      </div>
    </section>
  )
}
