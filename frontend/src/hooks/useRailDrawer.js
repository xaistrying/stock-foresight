import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * State of the Rail drawer (the 768 to 1143 px layout). The topbar "Tickers" button toggles it;
 * typing into the search opens it without moving focus; Escape closes it and puts focus back on the
 * button; a click outside it closes it. It is never modal: the search must stay usable while it is
 * open, so nothing here traps focus or makes the page inert.
 *
 * A drawer the user opened with the button stays open when the search is cleared; one that typing
 * opened closes again when the search is emptied.
 *
 * @param {{layoutMode: string, drawerId: string}} options
 */
export function useRailDrawer({ layoutMode, drawerId }) {
  const [open, setOpen] = useState(false)
  const openedBy = useRef(null)
  const buttonRef = useRef(null)
  const isOpen = open && layoutMode === 'drawer'

  // Leaving the drawer layout closes it for good: it must not reopen by itself on the way back.
  useEffect(() => {
    if (layoutMode !== 'drawer') setOpen(false)
  }, [layoutMode])

  const close = useCallback(({ focusButton = false } = {}) => {
    setOpen(false)
    openedBy.current = null
    if (focusButton) buttonRef.current?.focus()
  }, [])

  const toggle = useCallback(() => {
    openedBy.current = 'button'
    setOpen((current) => !current)
  }, [])

  /** The search text changed: typing opens the drawer, emptying the search closes one typing opened. */
  const onQueryChange = useCallback(
    (value) => {
      if (layoutMode !== 'drawer') return
      if (value && !open) {
        openedBy.current = 'typing'
        setOpen(true)
      } else if (!value && open && openedBy.current === 'typing') {
        close()
      }
    },
    [layoutMode, open, close],
  )

  useEffect(() => {
    if (!isOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') close({ focusButton: true })
    }
    // A press anywhere that is not the drawer, its button or the search (which must stay usable).
    const onPointerDown = (event) => {
      const inside =
        document.getElementById(drawerId)?.contains(event.target) ||
        buttonRef.current?.contains(event.target) ||
        event.target.closest?.('[role="search"]')
      if (!inside) close()
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [isOpen, close, drawerId])

  return { isOpen, buttonRef, toggle, close, onQueryChange }
}
