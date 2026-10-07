import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEME_STORAGE_KEY, useTheme } from './useTheme'
import { resetViewport, setViewport } from '../test/viewport'

const root = document.documentElement

beforeEach(() => {
  root.removeAttribute('data-theme')
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  resetViewport()
})

describe('useTheme', () => {
  it('starts from the stored choice', () => {
    setViewport(1440, { dark: false })
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBe('dark')
    expect(root.getAttribute('data-theme')).toBe('dark')
  })

  it('falls back to the operating system when nothing is stored', () => {
    setViewport(1440, { dark: true })

    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBe('dark')
  })

  it('ignores a stored value that is not a theme', () => {
    setViewport(1440, { dark: false })
    localStorage.setItem(THEME_STORAGE_KEY, 'purple')

    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBe('light')
  })

  it('toggle sets data-theme synchronously, stores the choice and flips the theme', () => {
    setViewport(1440, { dark: false })
    const { result } = renderHook(() => useTheme())

    act(() => {
      result.current.toggle()
      expect(root.getAttribute('data-theme')).toBe('dark')
    })

    expect(result.current.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')

    act(() => result.current.toggle())

    expect(result.current.theme).toBe('light')
    expect(root.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  it('shares one theme between every component that reads it', () => {
    setViewport(1440, { dark: false })
    const first = renderHook(() => useTheme())
    const second = renderHook(() => useTheme())

    act(() => first.result.current.toggle())

    expect(second.result.current.theme).toBe('dark')
  })

  it('still toggles for the session when storage throws on read and on write', () => {
    setViewport(1440, { dark: false })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')

    act(() => result.current.toggle())

    expect(result.current.theme).toBe('dark')
    expect(root.getAttribute('data-theme')).toBe('dark')
  })

  it('follows an operating-system change while no choice is stored', () => {
    const viewport = setViewport(1440, { dark: false })
    const { result } = renderHook(() => useTheme())

    act(() => viewport.setDark(true))

    expect(result.current.theme).toBe('dark')
  })

  it('keeps the chosen theme when the operating system changes afterwards', () => {
    const viewport = setViewport(1440, { dark: false })
    const { result } = renderHook(() => useTheme())
    act(() => result.current.toggle()) // dark, chosen

    act(() => viewport.setDark(false))
    act(() => viewport.setDark(true))
    act(() => viewport.setDark(false))

    expect(result.current.theme).toBe('dark')
  })
})
