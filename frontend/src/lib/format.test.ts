import { describe, it, expect } from 'vitest'
import { fmtSport } from './format'

describe('fmtSport', () => {
  it('maps known lowercase sports', () => {
    expect(fmtSport('cycling')).toBe('Ride')
    expect(fmtSport('ride')).toBe('Ride')
    expect(fmtSport('virtualride')).toBe('Virtual Ride')
    expect(fmtSport('mountainbikeride')).toBe('Mountain Bike')
    expect(fmtSport('gravelride')).toBe('Gravel Ride')
    expect(fmtSport('ebikeride')).toBe('E-Bike Ride')
    expect(fmtSport('run')).toBe('Run')
    expect(fmtSport('trailrun')).toBe('Trail Run')
    expect(fmtSport('swim')).toBe('Swim')
    expect(fmtSport('openwaterswim')).toBe('Swim')
    expect(fmtSport('hike')).toBe('Hike')
    expect(fmtSport('walk')).toBe('Walk')
    expect(fmtSport('yoga')).toBe('Yoga')
  })

  it('is case-insensitive', () => {
    expect(fmtSport('VirtualRide')).toBe('Virtual Ride')
    expect(fmtSport('RIDE')).toBe('Ride')
    expect(fmtSport('MountainBikeRide')).toBe('Mountain Bike')
    expect(fmtSport('TrailRun')).toBe('Trail Run')
  })

  it('maps synonym sports', () => {
    expect(fmtSport('strength_training')).toBe('Weight Training')
    expect(fmtSport('weighttraining')).toBe('Weight Training')
    expect(fmtSport('emountainbikeride')).toBe('E-Mountain Bike')
  })

  it('title-cases unknown sports', () => {
    expect(fmtSport('rollerski')).toBe('Rollerski')
    expect(fmtSport('rowing')).toBe('Rowing')
  })

  it('splits camelCase unknown sports', () => {
    expect(fmtSport('StandUpPaddling')).toBe('Stand Up Paddling')
    expect(fmtSport('RockClimbing')).toBe('Rock Climbing')
  })

  it('handles null, undefined, and empty string', () => {
    expect(fmtSport(null)).toBe('Activity')
    expect(fmtSport(undefined)).toBe('Activity')
    expect(fmtSport('')).toBe('Activity')
  })
})
