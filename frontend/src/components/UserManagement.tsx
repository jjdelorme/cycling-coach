import { useState, useEffect } from 'react'
import { fetchUsers, createUser, updateUserRole, deleteUser, type UserRecord } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Users, UserPlus, Trash2, Shield, Mail, Calendar, RefreshCw } from 'lucide-react'
import { fmtDateShort } from '../lib/format'

const ROLE_OPTIONS = [
  { value: 'none', label: 'None' },
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
  const [processing, setProcessing] = useState(false)

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
    setProcessing(true)
    try {
      await createUser(newEmail.trim(), newRole)
      setNewEmail('')
      setNewRole('read')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add user')
    } finally {
      setProcessing(false)
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
    if (!confirm(`Are you sure you want to remove access for ${email}?`)) return
    setError('')
    try {
      await deleteUser(email)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete user')
    }
  }

  if (loading) {
    return <div className="py-12 text-center text-text-muted animate-pulse font-bold uppercase tracking-widest text-xs">Loading authorized users...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-3">
            <Users size={24} className="text-accent" />
            User Management
          </h1>
          <p className="text-text-muted text-xs font-medium mt-1">Control access and permission levels for the coaching platform.</p>
        </div>
      </div>

      {error && (
        <div className="bg-red/10 border border-red/20 text-red text-xs font-bold px-4 py-3 rounded-lg animate-in shake duration-300">
          {error.toUpperCase()}
        </div>
      )}

      <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-md">
        <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
          <Shield size={18} className="text-accent" />
          <h3 className="text-sm font-bold text-text uppercase tracking-wider">Authorized Access List</h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] font-bold text-text-muted uppercase tracking-widest bg-surface-low/50 border-b border-border">
                <th className="py-3 px-5 text-left">Identity</th>
                <th className="py-3 px-5 text-left">Permission Role</th>
                <th className="py-3 px-5 text-left">Activity</th>
                <th className="py-3 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {users.map((u) => {
                const isSelf = u.email === currentUser?.email
                return (
                  <tr key={u.email} className="text-text hover:bg-surface2/30 transition-colors">
                    <td className="py-4 px-5">
                      <div className="flex items-center gap-3">
                        {u.avatar_url ? (
                          <img src={u.avatar_url} className="w-8 h-8 rounded-full border border-border" alt="" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center text-xs font-bold text-accent">
                            {(u.display_name || u.email).charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-bold text-sm">{u.display_name || u.email.split('@')[0]}</div>
                          <div className="text-[10px] font-mono text-text-muted flex items-center gap-1 opacity-60">
                            <Mail size={10} /> {u.email}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 px-5">
                      {isSelf ? (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-accent/10 text-accent text-[10px] font-black uppercase tracking-widest rounded-full border border-accent/20">
                          {u.role} (YOU)
                        </span>
                      ) : (
                        <select
                          value={u.role}
                          onChange={(e) => handleRoleChange(u.email, e.target.value)}
                          className="bg-surface-low text-text border border-border rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-tighter focus:outline-none focus:border-accent appearance-none cursor-pointer"
                        >
                          {ROLE_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td className="py-4 px-5">
                      <div className="flex items-center gap-1.5 text-[10px] font-bold text-text-muted uppercase tracking-tighter">
                        <Calendar size={12} />
                        {u.last_login ? fmtDateShort(u.last_login) : 'Never Active'}
                      </div>
                    </td>
                    <td className="py-4 px-5 text-right">
                      {!isSelf && (
                        <button
                          onClick={() => handleDelete(u.email)}
                          className="p-2 text-text-muted hover:text-red hover:bg-red/5 rounded-lg transition-all"
                          title="Revoke Access"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Add user form */}
        <div className="p-6 bg-surface-low/50 border-t border-border">
          <div className="flex flex-col md:flex-row items-end gap-4">
            <div className="flex-1 w-full space-y-1.5">
              <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">Authorize New User</label>
              <div className="relative">
                <input
                  type="email"
                  placeholder="name@gmail.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                  className="w-full bg-surface-low text-text border border-border rounded-lg px-10 py-2.5 text-sm focus:outline-none focus:border-accent transition-all"
                />
                <UserPlus size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted opacity-40" />
              </div>
            </div>
            <div className="w-full md:w-48 space-y-1.5">
              <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">Access Level</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm font-bold uppercase tracking-tighter focus:outline-none focus:border-accent appearance-none cursor-pointer"
              >
                {ROLE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleAdd}
              disabled={processing || !newEmail.trim()}
              className="w-full md:w-auto px-8 py-2.5 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all shadow-lg shadow-accent/20 flex items-center justify-center gap-2"
            >
              {processing ? <RefreshCw size={14} className="animate-spin" /> : <UserPlus size={14} />}
              Grant Access
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
