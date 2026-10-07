import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RailRow } from './RailRow'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { daysAgo, ELIGIBLE, ineligible, newQueryClient, renderWithQuery } from '../../test/railFixtures'

function renderRow(rowOverrides = {}, props = {}, queryClient = newQueryClient()) {
  const row = { ticker: 'TCB', loadedAt: daysAgo(28), eligibility: ELIGIBLE, ...rowOverrides }
  const onSelect = vi.fn()
  const view = renderWithQuery(
    <ul>
      <RailRow row={row} isSelected={false} onSelect={onSelect} {...props} />
    </ul>,
    queryClient,
  )
  return { onSelect, queryClient, ...view }
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('RailRow content', () => {
  it('shows the symbol and how long ago it was loaded, and no tag, for an eligible ticker', () => {
    const { container } = renderRow()

    expect(screen.getByRole('button', { name: /^TCB/ })).toHaveTextContent('TCB')
    expect(screen.getByText('Loaded 28d ago')).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/Delisted|Short history|Stale|Data gaps|Quality flag|No indicators/)
  })

  it.each([
    ['delisted', 'Delisted'],
    ['insufficient_history', 'Short history'],
    ['stale', 'Stale'],
    ['near_gap', 'Data gaps'],
    ['hard_quality_flag', 'Quality flag'],
    ['indicators_missing', 'No indicators'],
  ])('tags a ticker whose reason is %s as "%s", in text', (reason, tag) => {
    renderRow({ eligibility: ineligible([reason]) })

    expect(screen.getByText(tag)).toBeInTheDocument()
  })

  it('shows only the first reason as the tag, and lists every reason in the name and the title', () => {
    renderRow({ eligibility: ineligible(['delisted', 'stale']) })

    expect(screen.getByText('Delisted')).toBeInTheDocument()
    expect(screen.queryByText('Stale')).not.toBeInTheDocument()
    const select = screen.getByRole('button', { name: /^TCB/ })
    expect(select).toHaveAccessibleName(/Delisted/)
    expect(select).toHaveAccessibleName(/Stale/)
    expect(select.getAttribute('title')).toMatch(/Delisted/)
    expect(select.getAttribute('title')).toMatch(/Stale/)
  })

  it('puts the symbol first in the accessible name, then the age, then the reasons', () => {
    renderRow({ eligibility: ineligible(['near_gap']) })

    expect(screen.getByRole('button', { name: 'TCB, Loaded 28d ago, Data gaps' })).toBeInTheDocument()
  })

  it.each([[null], [undefined]])('shows no tag and no age claim when eligibility is %s', (eligibility) => {
    const { container } = renderRow({ eligibility })

    expect(screen.getByRole('button', { name: 'TCB, Loaded 28d ago' })).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/Delisted|Short history|Stale|Data gaps|Quality flag|No indicators|sessions? old/)
  })

  it('says "Loaded just now" for a row with a client-side load time of now', () => {
    renderRow({ loadedAt: new Date().toISOString(), eligibility: null })

    expect(screen.getByText('Loaded just now')).toBeInTheDocument()
  })

  it('shows no age text when there is no load time', () => {
    renderRow({ loadedAt: null })

    expect(screen.queryByText(/^Loaded/)).not.toBeInTheDocument()
  })

  it('marks the selected row with aria-current and no other row', () => {
    renderRow({}, { isSelected: true })

    expect(screen.getByRole('button', { name: /^TCB/ })).toHaveAttribute('aria-current', 'true')
  })

  it('does not mark an unselected row', () => {
    renderRow()

    expect(screen.getByRole('button', { name: /^TCB/ })).not.toHaveAttribute('aria-current')
  })

  it('selects its ticker when the row is activated', async () => {
    const { onSelect } = renderRow()

    await userEvent.click(screen.getByRole('button', { name: /^TCB/ }))

    expect(onSelect).toHaveBeenCalledWith('TCB')
  })
})

describe('RailRow has no star', () => {
  it('keeps the row to the symbol, its age, its tag and Refresh: favoriting is done from the Stage header', () => {
    renderRow()

    expect(screen.queryByRole('button', { name: /favorite/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual([
      'TCB, Loaded 28d ago',
      'Refresh TCB',
    ])
  })
})

describe('RailRow carries no direction cue', () => {
  it.each([
    ['eligible', ELIGIBLE],
    ['stale', ineligible(['stale'])],
    ['delisted and stale', ineligible(['delisted', 'stale'])],
    ['unknown', null],
  ])('a %s row has no arrow, no percentage and no status dot', (_name, eligibility) => {
    const { container } = renderRow({ eligibility }, { isSelected: true })

    expect(container).not.toHaveTextContent(/[↑↓▲▼→]/)
    expect(container).not.toHaveTextContent(/%/)
    expect(container.querySelector('[class*="dot"], [role="img"], [data-direction], [data-status], [data-freshness]')).toBeNull()
  })
})

describe('RailRow refresh', () => {
  it('has a Refresh control that is in the tab order after the row, without hovering', async () => {
    renderRow()

    await userEvent.tab()
    expect(screen.getByRole('button', { name: /^TCB/ })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Refresh TCB' })).toHaveFocus()
  })

  it('calls POST /tickers/{ticker}/load without changing the selection', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
    const { onSelect } = renderRow()

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))

    await waitFor(() => expect(load).toHaveBeenCalledWith('TCB'))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('disables Refresh while its own request is in flight', async () => {
    let resolveLoad
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(new Promise((resolve) => (resolveLoad = resolve)))
    renderRow()
    const refresh = screen.getByRole('button', { name: 'Refresh TCB' })

    await userEvent.click(refresh)
    await waitFor(() => expect(refresh).toBeDisabled())

    resolveLoad({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
    await waitFor(() => expect(refresh).not.toBeDisabled())
  })

  it.each([
    ['rate_limited', /try again in a moment/i],
    ['invalid_symbol', /"TCB" isn't a recognized ticker symbol/i],
    ['no_data', /unlikely to help/i],
  ])('says so, in its own words, when the load answers %s', async (status, message) => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status })
    renderRow()

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))

    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('separates a server error from a network failure', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker')
    load.mockRejectedValueOnce(new ApiError('Server error', { status: 500, body: null }))
    renderRow()

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))
    expect(await screen.findByText('Something went wrong — try again')).toBeInTheDocument()

    load.mockRejectedValueOnce(new TypeError('fetch failed'))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))
    expect(await screen.findByText('Network error — try again')).toBeInTheDocument()
  })

  it('invalidates the catalog, history and range of that ticker, and nothing else, when it succeeds', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
    const queryClient = newQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    renderRow({}, {}, queryClient)

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([filters]) => filters.queryKey)).toEqual([
      ['tickers'],
      ['ticker-history', 'TCB'],
      ['ticker-range', 'TCB'],
    ])
  })

  it('invalidates nothing when it does not complete with ok', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'rate_limited' })
    const queryClient = newQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    renderRow({}, {}, queryClient)

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))

    await screen.findByText(/try again in a moment/i)
    expect(invalidate).not.toHaveBeenCalled()
  })
})
