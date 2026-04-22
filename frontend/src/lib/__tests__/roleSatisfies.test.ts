import { describe, it, expect } from 'vitest'
import { roleSatisfies } from '../routes'

describe('roleSatisfies', () => {
  it('returns false for "none" against any required role', () => {
    expect(roleSatisfies('none', 'read')).toBe(false)
    expect(roleSatisfies('none', 'readwrite')).toBe(false)
    expect(roleSatisfies('none', 'admin')).toBe(false)
  })

  it('returns false for undefined / null actual roles', () => {
    expect(roleSatisfies(undefined, 'read')).toBe(false)
    expect(roleSatisfies(null, 'admin')).toBe(false)
  })

  it('returns false for unknown role strings', () => {
    expect(roleSatisfies('hacker', 'read')).toBe(false)
  })

  it('returns true when no required role is supplied', () => {
    expect(roleSatisfies('none', undefined)).toBe(true)
    expect(roleSatisfies(undefined, undefined)).toBe(true)
  })

  it('respects the role hierarchy: admin > readwrite > read', () => {
    expect(roleSatisfies('admin', 'admin')).toBe(true)
    expect(roleSatisfies('admin', 'readwrite')).toBe(true)
    expect(roleSatisfies('admin', 'read')).toBe(true)
    expect(roleSatisfies('readwrite', 'admin')).toBe(false)
    expect(roleSatisfies('readwrite', 'readwrite')).toBe(true)
    expect(roleSatisfies('readwrite', 'read')).toBe(true)
    expect(roleSatisfies('read', 'admin')).toBe(false)
    expect(roleSatisfies('read', 'readwrite')).toBe(false)
    expect(roleSatisfies('read', 'read')).toBe(true)
  })
})
