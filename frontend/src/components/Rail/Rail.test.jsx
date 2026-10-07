import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Rail } from './Rail'
import { FAVORITES_STORAGE_KEY, resetFavoritesCache, useFavorites } from '../../hooks/useFavorites'
import * as tickersApi from '../../api/tickers'
import { catalogEntry, daysAgo, ineligible, renderWithQuery } from '../../test/railFixtures'
import { declarations, readSrc, rulesFor } from '../../test/cssText'

function renderRail(props = {}, tickers = []) {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers })
  const onSelectTicker = vi.fn()
  const merged = {
    mode: 'wide',
    selectedTicker: null,
    onSelectTicker,
    searched: [],
    query: '',
    ...props,
  }
  return { onSelectTicker, ...renderWithQuery(<Rail {...merged} />) }
}

const rowNames = () =>
  screen
    .getAllByRole('button', { name: /^[A-Z0-9]+(,|$)/ })
    .map((button) => button.getAttribute('aria-label').split(',')[0])

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  resetFavoritesCache()
})

describe('Rail contents', () => {
  it('is a navigation landmark named Tickers with an "All tickers" heading and no tile grid', async () => {
    renderRail({}, [catalogEntry('TCB')])

    await screen.findByRole('button', { name: /^TCB/ })
    const nav = screen.getByRole('navigation', { name: 'Tickers' })

    expect(within(nav).getByRole('heading', { name: 'All tickers' })).toBeInTheDocument()
    expect(within(nav).queryByRole('heading', { name: 'Watchlist' })).not.toBeInTheDocument()
    expect(within(nav).getByRole('list')).toBeInTheDocument()
    expect(within(nav).getAllByRole('listitem')).toHaveLength(1)
  })

  it('lists loaded catalog entries only', async () => {
    renderRail({}, [
      catalogEntry('TCB'),
      catalogEntry('VIB', { loaded: false, last_loaded_at: null, eligibility: null }),
      catalogEntry('HPG'),
    ])

    await screen.findByRole('button', { name: /^TCB/ })

    expect(rowNames()).toEqual(['HPG', 'TCB'])
    expect(screen.queryByRole('button', { name: /^VIB/ })).not.toBeInTheDocument()
  })

  it('shows 207 rows when 207 of 208 catalog entries are loaded', { timeout: 30_000 }, async () => {
    const tickers = Array.from({ length: 208 }, (_, i) =>
      catalogEntry(`T${String(i).padStart(3, '0')}`, i === 100 ? { loaded: false, eligibility: null } : {}),
    )
    renderRail({}, tickers)

    await screen.findByRole('button', { name: /^T000/ })

    // Counted on the list itself: a role query over 207 rows is slow under jsdom.
    expect(document.querySelectorAll('#rail-list li')).toHaveLength(207)
  })

  it('rows are ordered by symbol, ignoring the order the catalog arrived in', async () => {
    renderRail({}, [catalogEntry('VIB'), catalogEntry('TCB'), catalogEntry('HPG')])

    await screen.findByRole('button', { name: /^TCB/ })

    expect(rowNames()).toEqual(['HPG', 'TCB', 'VIB'])
  })

  it('has no search or text input of its own, only the sort control', async () => {
    renderRail({}, [catalogEntry('TCB')])

    const nav = await screen.findByRole('navigation', { name: 'Tickers' })

    expect(within(nav).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(nav).queryByRole('searchbox')).not.toBeInTheDocument()
    expect(within(nav).queryByRole('search')).not.toBeInTheDocument()
    expect(within(nav).getAllByRole('combobox').map((el) => el.getAttribute('aria-label'))).toEqual(['Sort tickers'])
  })
})

describe('Rail watchlist (favorites)', () => {
  const tickers = [catalogEntry('AAA'), catalogEntry('BBB'), catalogEntry('CCC'), catalogEntry('DDD')]
  // The star lives in the Stage header; this probe reads and writes the same shared list.
  function Probe() {
    const { toggle } = useFavorites()
    return (
      <>
        {['AAA', 'CCC'].map((symbol) => (
          <button key={symbol} type="button" onClick={() => toggle(symbol)}>
            {`star ${symbol}`}
          </button>
        ))}
      </>
    )
  }
  const renderWithProbe = (props = {}) => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers })
    return renderWithQuery(
      <>
        <Probe />
        <Rail mode="wide" selectedTicker={null} onSelectTicker={vi.fn()} searched={[]} query="" {...props} />
      </>,
    )
  }
  const star = (symbol) => screen.getByRole('button', { name: `star ${symbol}` })

  it('has no Watchlist section until a ticker is starred', async () => {
    renderRail({}, tickers)
    await screen.findByRole('button', { name: /^AAA/ })

    expect(screen.queryByRole('heading', { name: 'Watchlist' })).not.toBeInTheDocument()
  })

  it('has no star of its own on a row', async () => {
    renderRail({}, tickers)
    await screen.findByRole('button', { name: /^AAA/ })

    expect(screen.queryByRole('button', { name: /favorite/i })).not.toBeInTheDocument()
  })

  it('moves a starred ticker to a Watchlist section above the rest, once', async () => {
    renderWithProbe()
    await screen.findByRole('button', { name: /^AAA/ })

    await userEvent.click(star('CCC'))

    const watchlist = screen.getByRole('heading', { name: 'Watchlist' }).closest('section')
    const rest = screen.getByRole('heading', { name: 'All tickers' }).closest('section')
    expect(within(watchlist).getByRole('button', { name: /^CCC/ })).toBeInTheDocument()
    expect(within(rest).queryByRole('button', { name: /^CCC/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^CCC/ })).toHaveLength(1)
    expect(rowNames()).toEqual(['CCC', 'AAA', 'BBB', 'DDD'])
  })

  it('puts a ticker back among the rest when its star is cleared', async () => {
    renderWithProbe()
    await screen.findByRole('button', { name: /^AAA/ })
    await userEvent.click(star('CCC'))

    await userEvent.click(star('CCC'))

    expect(screen.queryByRole('heading', { name: 'Watchlist' })).not.toBeInTheDocument()
    expect(rowNames()).toEqual(['AAA', 'BBB', 'CCC', 'DDD'])
  })

  it('shows the favorites stored from an earlier visit', async () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['DDD', 'BBB']))
    renderRail({}, tickers)

    await screen.findByRole('button', { name: /^AAA/ })

    expect(rowNames()).toEqual(['BBB', 'DDD', 'AAA', 'CCC']) // watchlist by the current sort, then the rest
  })

  it('applies the search to the watchlist too', async () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['AAA', 'BBB', 'DDD']))
    renderRail({ query: 'b' }, tickers)

    await screen.findByRole('button', { name: /^BBB/ })

    expect(rowNames()).toEqual(['BBB'])
  })

  it('applies the sort to the watchlist too', async () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['AAA', 'BBB']))
    const older = daysAgo(9)
    const newer = daysAgo(1)
    renderRail({}, [
      catalogEntry('AAA', { last_loaded_at: older }),
      catalogEntry('BBB', { last_loaded_at: newer }),
      catalogEntry('CCC'),
    ])
    await screen.findByRole('button', { name: /^AAA/ })

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(rowNames().slice(0, 2)).toEqual(['BBB', 'AAA'])
  })

  it('keeps a starred ticker selectable, and selecting it works as before', async () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['CCC']))
    const { onSelectTicker } = renderRail({}, tickers)

    await userEvent.click(await screen.findByRole('button', { name: /^CCC/ }))

    expect(onSelectTicker).toHaveBeenCalledWith('CCC')
  })

  it('makes no request to star or unstar', async () => {
    renderWithProbe()
    await screen.findByRole('button', { name: /^AAA/ })

    await userEvent.click(star('AAA'))
    await userEvent.click(star('AAA'))

    expect(tickersApi.fetchTickers).toHaveBeenCalledTimes(1)
  })
})

describe('Rail scroll position on a sort change', () => {
  it('goes back to the top of the list when the sort changes', async () => {
    renderRail({}, [catalogEntry('AAA'), catalogEntry('BBB'), catalogEntry('CCC')])
    await screen.findByRole('button', { name: /^AAA/ })
    const nav = screen.getByRole('navigation', { name: 'Tickers' })
    nav.scrollTop = 400

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(nav.scrollTop).toBe(0)
  })

  it('does not let the browser anchor the scroll to a row that has moved', () => {
    const css = readSrc('components/Rail/rail.css')
    const [rule] = rulesFor(css, '.rail')

    expect(declarations(rule.body)['overflow-anchor']).toBe('none')
  })
})

describe('Rail sort', () => {
  const yesterday = daysAgo(1) // one instant, so BBB and DDD tie exactly
  const tickers = [
    catalogEntry('AAA', { last_loaded_at: daysAgo(5) }),
    catalogEntry('BBB', { last_loaded_at: yesterday }),
    catalogEntry('CCC', { last_loaded_at: null }),
    catalogEntry('DDD', { last_loaded_at: yesterday }),
    catalogEntry('EEE', { last_loaded_at: daysAgo(30) }),
  ]

  it('offers exactly two options, Symbol first', async () => {
    renderRail({}, tickers)

    const select = await screen.findByRole('combobox', { name: 'Sort tickers' })

    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Symbol', 'Last loaded'])
    expect(select).toHaveValue('symbol')
  })

  it('orders by last load, newest first, rows without a load time last and ties by symbol', async () => {
    renderRail({}, tickers)
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(rowNames()).toEqual(['BBB', 'DDD', 'AAA', 'EEE', 'CCC'])
  })

  it('goes back to A to Z', async () => {
    renderRail({}, tickers)
    const select = await screen.findByRole('combobox', { name: 'Sort tickers' })
    await userEvent.selectOptions(select, 'Last loaded')

    await userEvent.selectOptions(select, 'Symbol')

    expect(rowNames()).toEqual(['AAA', 'BBB', 'CCC', 'DDD', 'EEE'])
  })

  it('issues no request when the sort changes', async () => {
    renderRail({}, tickers)
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(tickersApi.fetchTickers).toHaveBeenCalledTimes(1)
  })
})

describe('Rail filter', () => {
  const tickers = [catalogEntry('CBB'), catalogEntry('ACB'), catalogEntry('VIB'), catalogEntry('TCB'), catalogEntry('HPG')]

  it('keeps only the rows whose symbol contains the search text, case-insensitively', async () => {
    renderRail({ query: 'cb' }, tickers)

    await screen.findByRole('button', { name: /^ACB/ })

    expect(rowNames()).toEqual(['ACB', 'CBB', 'TCB'])
  })

  it('announces how many of how many in a polite live region', async () => {
    renderRail({ query: 'CB' }, tickers)

    await screen.findByRole('button', { name: /^ACB/ })

    const region = screen.getByText('3 of 5 tickers')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('announces nothing while the search is empty', async () => {
    renderRail({ query: '' }, tickers)

    await screen.findByRole('button', { name: /^ACB/ })

    expect(document.querySelector('[aria-live="polite"]')).toHaveTextContent('')
  })

  it('leaves the selection alone', async () => {
    const { onSelectTicker } = renderRail({ query: 'CB', selectedTicker: 'HPG' }, tickers)

    await screen.findByRole('button', { name: /^ACB/ })

    expect(onSelectTicker).not.toHaveBeenCalled()
  })

  it('says nothing matches and that Enter loads the symbol', async () => {
    renderRail({ query: 'zzz' }, tickers)

    expect(await screen.findByText('No ticker in the Rail matches "ZZZ". Press Enter to load it.')).toBeInTheDocument()
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })
})

describe('Rail searched-in tickers', () => {
  it('lists a symbol the catalog does not list as an ordinary row, "Loaded just now", with no tag', async () => {
    renderRail({ searched: [{ ticker: 'FPT', loadedAt: new Date().toISOString() }] }, [catalogEntry('TCB')])

    expect(await screen.findByRole('button', { name: 'FPT, Loaded just now' })).toBeInTheDocument()
    await screen.findByRole('button', { name: /^TCB/ })
    expect(screen.queryByRole('heading', { name: /searched/i })).not.toBeInTheDocument()
    expect(rowNames()).toEqual(['FPT', 'TCB'])
  })

  it('lists a searched-in symbol once when the refetched catalog now lists it', async () => {
    renderRail({ searched: [{ ticker: 'TCB', loadedAt: new Date().toISOString() }] }, [catalogEntry('TCB')])

    await screen.findByRole('button', { name: /^TCB/ })

    expect(rowNames()).toEqual(['TCB'])
  })

  it('sorts a searched-in row among the others by the current sort', async () => {
    renderRail({ searched: [{ ticker: 'ZZZ', loadedAt: new Date().toISOString() }] }, [
      catalogEntry('AAA', { last_loaded_at: daysAgo(3) }),
    ])
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(rowNames()).toEqual(['ZZZ', 'AAA'])
  })

  it('has a Refresh control on it, like any other row', async () => {
    renderRail({ searched: [{ ticker: 'FPT', loadedAt: new Date().toISOString() }] }, [])

    expect(await screen.findByRole('button', { name: 'Refresh FPT' })).toBeInTheDocument()
  })
})

describe('Rail selection', () => {
  afterEach(() => {
    delete HTMLElement.prototype.scrollIntoView
  })

  const installScrollSpy = () => {
    const spy = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, writable: true, value: spy })
    return spy
  }

  it('marks only the selected row with aria-current', async () => {
    renderRail({ selectedTicker: 'TCB' }, [catalogEntry('TCB'), catalogEntry('VIB')])

    expect(await screen.findByRole('button', { name: /^TCB/ })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /^VIB/ })).not.toHaveAttribute('aria-current')
  })

  it('selects a row when it is chosen', async () => {
    const { onSelectTicker } = renderRail({}, [catalogEntry('TCB')])

    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
  })

  it('scrolls the selected row into view, nearest edge only', async () => {
    const scrollIntoView = installScrollSpy()
    renderRail({ selectedTicker: 'VIB' }, [catalogEntry('TCB'), catalogEntry('VIB')])
    await screen.findByRole('button', { name: /^VIB/ })

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))

    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
    expect(within(scrollIntoView.mock.contexts[0]).getByRole('button', { name: /^VIB/ })).toBeInTheDocument()
  })

  it('does not scroll to the selected row again when the sort changes: the list starts at its top', async () => {
    const scrollIntoView = installScrollSpy()
    renderRail({ selectedTicker: 'CCC' }, [catalogEntry('AAA'), catalogEntry('BBB'), catalogEntry('CCC')])
    await screen.findByRole('button', { name: /^CCC/ })
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    const nav = screen.getByRole('navigation', { name: 'Tickers' })
    nav.scrollTop = 300

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')

    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    expect(nav.scrollTop).toBe(0)
  })

  it('scrolls to a row when it becomes the selection', async () => {
    const scrollIntoView = installScrollSpy()
    const { rerender, queryClient } = renderRail({ selectedTicker: null }, [catalogEntry('AAA'), catalogEntry('BBB')])
    await screen.findByRole('button', { name: /^AAA/ })
    expect(scrollIntoView).not.toHaveBeenCalled()

    rerender(
      <QueryClientProvider client={queryClient}>
        <Rail mode="wide" selectedTicker="BBB" onSelectTicker={vi.fn()} searched={[]} query="" />
      </QueryClientProvider>,
    )

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    expect(within(scrollIntoView.mock.contexts[0]).getByRole('button', { name: /^BBB/ })).toBeInTheDocument()
  })

  it('scrolls nothing when no ticker is selected', async () => {
    const scrollIntoView = installScrollSpy()
    renderRail({ selectedTicker: null }, [catalogEntry('TCB')])
    await screen.findByRole('button', { name: /^TCB/ })

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('Rail states', () => {
  it('shows skeleton rows, hidden from assistive technology, while the catalog loads', () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockReturnValue(new Promise(() => {}))
    renderWithQuery(<Rail mode="wide" selectedTicker={null} onSelectTicker={vi.fn()} searched={[]} query="" />)

    const skeletons = document.querySelectorAll('.rail-row--skeleton')

    expect(skeletons.length).toBeGreaterThanOrEqual(3)
    for (const skeleton of skeletons) expect(skeleton).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryAllByRole('button', { name: /^[A-Z]/ })).toHaveLength(0)
  })

  it('says the list could not be loaded when the catalog request fails', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockRejectedValue(new Error('down'))
    renderWithQuery(<Rail mode="wide" selectedTicker={null} onSelectTicker={vi.fn()} searched={[]} query="" />)

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the ticker list — please refresh.")
  })

  it('tags rows from the catalog entry and not from any request of its own', async () => {
    renderRail({}, [catalogEntry('TCB', { eligibility: ineligible(['stale']) }), catalogEntry('VIB')])

    expect(await screen.findByText('Stale')).toBeInTheDocument()
    expect(screen.getAllByText(/^Stale$/)).toHaveLength(1)
    expect(tickersApi.fetchTickers).toHaveBeenCalledTimes(1)
  })
})

describe('Collapsed Rail', () => {
  const tickers = [catalogEntry('TCB', { eligibility: ineligible(['stale']) }), catalogEntry('VIB')]

  it('has no toggle in wide mode', async () => {
    renderRail({ mode: 'wide' }, tickers)
    await screen.findByRole('button', { name: /^TCB/ })

    expect(screen.queryByRole('button', { name: /show full ticker list/i })).not.toBeInTheDocument()
  })

  it('pins open with its toggle, which carries aria-expanded and aria-controls', async () => {
    renderRail({ mode: 'collapsed' }, tickers)
    const toggle = await screen.findByRole('button', { name: /show full ticker list/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById(toggle.getAttribute('aria-controls'))).toBeInTheDocument()

    await userEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes on Escape and puts focus back on the toggle', async () => {
    renderRail({ mode: 'collapsed' }, tickers)
    const toggle = await screen.findByRole('button', { name: /show full ticker list/i })
    await userEvent.click(toggle)
    await userEvent.tab() // into the rows

    await userEvent.keyboard('{Escape}')

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveFocus()
  })

  it('closes when a row is chosen, and selects it', async () => {
    const { onSelectTicker } = renderRail({ mode: 'collapsed' }, tickers)
    const toggle = await screen.findByRole('button', { name: /show full ticker list/i })
    await userEvent.click(toggle)

    await userEvent.click(screen.getByRole('button', { name: /^VIB/ }))

    expect(onSelectTicker).toHaveBeenCalledWith('VIB')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not trap focus, and does not make the rest of the page inert or modal', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers })
    renderWithQuery(
      <>
        <button type="button">Before</button>
        <Rail mode="collapsed" selectedTicker={null} onSelectTicker={vi.fn()} searched={[]} query="" />
        <main>
          <button type="button">After</button>
        </main>
      </>,
    )
    const toggle = await screen.findByRole('button', { name: /show full ticker list/i })
    await userEvent.click(toggle)

    for (let i = 0; i < 12; i += 1) await userEvent.tab()

    expect(document.querySelector('[inert], [aria-modal="true"]')).toBeNull()
    expect(screen.getByRole('main')).not.toHaveAttribute('inert')
  })

  it('gives a row the same accessible name collapsed and expanded, and wide', async () => {
    const { unmount } = renderRail({ mode: 'wide' }, tickers)
    const wide = (await screen.findByRole('button', { name: /^TCB/ })).getAttribute('aria-label')
    unmount()

    renderRail({ mode: 'collapsed' }, tickers)
    const collapsed = (await screen.findByRole('button', { name: /^TCB/ })).getAttribute('aria-label')
    await userEvent.click(screen.getByRole('button', { name: /show full ticker list/i }))
    const expanded = screen.getByRole('button', { name: /^TCB/ }).getAttribute('aria-label')

    expect(wide).toMatch(/Stale/)
    expect(collapsed).toBe(wide)
    expect(expanded).toBe(wide)
  })
})

describe('Rail as a drawer', () => {
  const drawerProps = { mode: 'drawer', id: 'ticker-drawer', selectedTicker: null, onSelectTicker: vi.fn(), searched: [], query: '' }

  it('is hidden while closed', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [catalogEntry('TCB')] })
    const { container } = renderWithQuery(<Rail {...drawerProps} drawerOpen={false} />)

    expect(container.querySelector('#ticker-drawer')).not.toBeVisible()
  })

  it('shows its rows when open and sets no aria-modal', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [catalogEntry('TCB')] })
    renderWithQuery(<Rail {...drawerProps} drawerOpen />)

    const nav = await screen.findByRole('navigation', { name: 'Tickers' })

    expect(nav).toBeVisible()
    expect(nav).toHaveAttribute('id', 'ticker-drawer')
    expect(nav).not.toHaveAttribute('aria-modal')
    expect(await screen.findByRole('button', { name: /^TCB/ })).toBeVisible()
  })

  it('has no collapsed-Rail toggle', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [catalogEntry('TCB')] })
    renderWithQuery(<Rail {...drawerProps} drawerOpen />)
    await screen.findByRole('button', { name: /^TCB/ })

    expect(screen.queryByRole('button', { name: /show full ticker list/i })).not.toBeInTheDocument()
  })
})
