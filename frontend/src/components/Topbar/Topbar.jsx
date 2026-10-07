import { useTheme } from '../../hooks/useTheme'
import './topbar.css'

/**
 * The fixed bar over the three zones: brand, the one ticker search (passed in as `search`),
 * the "Tickers" button that opens the Rail drawer (only in `drawer` mode, where the Rail is not
 * a column), and the theme toggle. The brand is not a heading: the page's only h1 is the
 * selected ticker in the Stage header.
 *
 * @param {{
 *   search: import('react').ReactNode,
 *   layoutMode: 'wide'|'collapsed'|'drawer'|'phone',
 *   drawerOpen?: boolean,
 *   drawerId?: string,
 *   drawerButtonRef?: import('react').Ref<HTMLButtonElement>,
 *   onToggleDrawer?: () => void,
 * }} props
 */
export function Topbar({ search, layoutMode, drawerOpen = false, drawerId, drawerButtonRef, onToggleDrawer }) {
  const { theme, toggle } = useTheme()

  return (
    <header className="topbar">
      <span className="topbar__brand">Stock Foresight</span>
      {layoutMode === 'drawer' ? (
        <button
          ref={drawerButtonRef}
          type="button"
          className="topbar__button"
          aria-expanded={drawerOpen}
          aria-controls={drawerId}
          onClick={onToggleDrawer}
        >
          Tickers
        </button>
      ) : null}
      <div className="topbar__search">{search}</div>
      <span className="topbar__spacer" />
      <button type="button" className="topbar__button" aria-pressed={theme === 'dark'} onClick={toggle}>
        Dark theme
      </button>
    </header>
  )
}
