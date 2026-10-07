import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FAVORITES_STORAGE_KEY, resetFavoritesCache, useFavorites } from './useFavorites'

beforeEach(() => {
  localStorage.clear()
  resetFavoritesCache()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useFavorites', () => {
  it('starts empty', () => {
    const { result } = renderHook(() => useFavorites())

    expect(result.current.favorites).toEqual([])
    expect(result.current.isFavorite('TCB')).toBe(false)
  })

  it('reads the stored favorites', () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['TCB', 'VIB']))

    const { result } = renderHook(() => useFavorites())

    expect(result.current.favorites).toEqual(['TCB', 'VIB'])
    expect(result.current.isFavorite('VIB')).toBe(true)
  })

  it.each([['not json'], ['{"a":1}'], ['[1,2]']])('ignores a stored value that is not a list of symbols (%s)', (raw) => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, raw)

    const { result } = renderHook(() => useFavorites())

    expect(result.current.favorites).toEqual([])
  })

  it('toggles a symbol on and off and stores the list', () => {
    const { result } = renderHook(() => useFavorites())

    act(() => result.current.toggle('TCB'))
    expect(result.current.isFavorite('TCB')).toBe(true)
    expect(JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY))).toEqual(['TCB'])

    act(() => result.current.toggle('TCB'))
    expect(result.current.isFavorite('TCB')).toBe(false)
    expect(JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY))).toEqual([])
  })

  it('shares one list between every component that reads it', () => {
    const first = renderHook(() => useFavorites())
    const second = renderHook(() => useFavorites())

    act(() => first.result.current.toggle('HPG'))

    expect(second.result.current.isFavorite('HPG')).toBe(true)
  })

  it('keeps the same list object while nothing changes, so readers do not re-render for nothing', () => {
    const { result, rerender } = renderHook(() => useFavorites())
    const before = result.current.favorites

    rerender()

    expect(result.current.favorites).toBe(before)
  })

  it('still works for the session when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const { result } = renderHook(() => useFavorites())

    act(() => result.current.toggle('TCB'))

    expect(result.current.isFavorite('TCB')).toBe(true)
  })

  it('follows a change made in another tab', () => {
    const { result } = renderHook(() => useFavorites())

    act(() => {
      localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['MWG']))
      window.dispatchEvent(new StorageEvent('storage', { key: FAVORITES_STORAGE_KEY }))
    })

    expect(result.current.isFavorite('MWG')).toBe(true)
  })
})
