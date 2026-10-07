import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useLayoutMode } from './useLayoutMode'
import { resetViewport, setViewport } from '../test/viewport'

afterEach(resetViewport)

describe('useLayoutMode', () => {
  it.each([
    [1440, 'wide'],
    [1920, 'wide'],
    [1300, 'collapsed'],
    [900, 'drawer'],
    [390, 'phone'],
  ])('returns the mode for a %ipx viewport on the first render', (width, mode) => {
    setViewport(width)

    const { result } = renderHook(() => useLayoutMode())

    expect(result.current).toBe(mode)
  })

  it('updates when the viewport crosses a breakpoint', () => {
    const viewport = setViewport(1500)
    const { result } = renderHook(() => useLayoutMode())
    expect(result.current).toBe('wide')

    act(() => viewport.setWidth(1143))
    expect(result.current).toBe('drawer')

    act(() => viewport.setWidth(500))
    expect(result.current).toBe('phone')

    act(() => viewport.setWidth(1200))
    expect(result.current).toBe('collapsed')
  })

  it('stops listening once unmounted', () => {
    const viewport = setViewport(1500)
    const { result, unmount } = renderHook(() => useLayoutMode())

    unmount()
    act(() => viewport.setWidth(500))

    expect(result.current).toBe('wide')
  })
})
