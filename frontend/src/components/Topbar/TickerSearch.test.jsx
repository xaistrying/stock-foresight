import { useState } from 'react'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TickerSearch } from './TickerSearch'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { daysAgo, ELIGIBLE, ineligible, newQueryClient, renderWithQuery } from '../../test/railFixtures'

const ROWS = [
  { ticker: 'TCB', loadedAt: daysAgo(3), eligibility: ELIGIBLE },
  { ticker: 'VIB', loadedAt: daysAgo(30), eligibility: ineligible(['stale']) },
  { ticker: 'VND', loadedAt: daysAgo(1), eligibility: ELIGIBLE },
  { ticker: 'VCB', loadedAt: daysAgo(2), eligibility: ELIGIBLE },
]

function Harness({ initial = '', ...props }) {
  const [value, setValue] = useState(initial)
  return <TickerSearch rows={ROWS} layoutMode="wide" value={value} onValueChange={setValue} {...props} />
}

function renderSearch(props = {}, queryClient = newQueryClient()) {
  const onSelectTicker = vi.fn()
  const onLoaded = vi.fn()
  const view = renderWithQuery(<Harness onSelectTicker={onSelectTicker} onLoaded={onLoaded} {...props} />, queryClient)
  return { onSelectTicker, onLoaded, queryClient, ...view }
}

const input = () => screen.getByLabelText(/search ticker/i)

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('TickerSearch', () => {
  it('is the page search: a search landmark with one input, the placeholder, and no Load button', () => {
    renderSearch()

    const form = screen.getByRole('search')

    expect(within(form).getAllByRole('textbox')).toHaveLength(1)
    expect(input()).toHaveAttribute('placeholder', 'Search ticker')
    expect(screen.queryByRole('button', { name: /load/i })).not.toBeInTheDocument()
  })

  it('upper-cases what is typed, reports every change, and stops at 12 characters', async () => {
    const onValueChange = vi.fn()
    renderWithQuery(<TickerSearch rows={ROWS} layoutMode="wide" value="" onValueChange={onValueChange} onSelectTicker={vi.fn()} onLoaded={vi.fn()} />)

    await userEvent.type(input(), 'tc')

    expect(onValueChange.mock.calls.map(([v]) => v)).toEqual(['T', 'C'])
    expect(input()).toHaveAttribute('maxlength', '12')
  })

  it('does nothing on Enter with an empty input', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker')
    const { onSelectTicker } = renderSearch()

    await userEvent.type(input(), '{Enter}')

    expect(onSelectTicker).not.toHaveBeenCalled()
    expect(load).not.toHaveBeenCalled()
  })

  it('selects a symbol that is in the Rail on Enter, with no request, and clears the input', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker')
    const { onSelectTicker } = renderSearch()

    await userEvent.type(input(), 'tcb{Enter}')

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
    expect(load).not.toHaveBeenCalled()
    expect(input()).toHaveValue('')
  })

  it('loads any other symbol on Enter, then selects it, tells the app it joined, and clears the input', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'ok', rows_loaded: 300 })
    const { onSelectTicker, onLoaded } = renderSearch()

    await userEvent.type(input(), 'zzz{Enter}')

    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('ZZZ'))
    expect(load).toHaveBeenCalledWith('ZZZ')
    expect(onLoaded).toHaveBeenCalledWith('ZZZ')
    expect(input()).toHaveValue('')
  })

  it('loads a catalog symbol that is not loaded yet (it is not in the Rail) before selecting it', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'HPG', status: 'ok', rows_loaded: 300 })
    const { onSelectTicker } = renderSearch()

    await userEvent.type(input(), 'HPG{Enter}')

    await waitFor(() => expect(load).toHaveBeenCalledWith('HPG'))
    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('HPG'))
  })

  it('puts focus back in the input once a load settles', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'ok', rows_loaded: 1 })
    renderSearch()

    await userEvent.type(input(), 'zzz{Enter}')

    await waitFor(() => expect(input()).toHaveFocus())
  })

  it('is disabled and busy, with a status line, while a load runs', async () => {
    let resolveLoad
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(new Promise((resolve) => (resolveLoad = resolve)))
    renderSearch()

    await userEvent.type(input(), 'ZZZ{Enter}')

    await waitFor(() => expect(input()).toBeDisabled())
    expect(input()).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toHaveTextContent('Loading ZZZ…')

    resolveLoad({ ticker: 'ZZZ', status: 'ok', rows_loaded: 1 })
    await waitFor(() => expect(input()).not.toBeDisabled())
    expect(input()).not.toHaveAttribute('aria-busy', 'true')
  })
})

describe('TickerSearch clear button', () => {
  it('is absent while the input is empty', () => {
    renderSearch()

    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
  })

  it('empties the input, tells the app, and puts focus back in the input', async () => {
    renderSearch()
    await userEvent.type(input(), 'vi')

    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))

    expect(input()).toHaveValue('')
    expect(input()).toHaveFocus()
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
  })

  it('also dismisses a failure message', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'no_data' })
    renderSearch()
    await userEvent.type(input(), 'ZZZ{Enter}')
    await screen.findByRole('alert')

    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('is not offered while a load is running', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(new Promise(() => {}))
    renderSearch()

    await userEvent.type(input(), 'ZZZ{Enter}')

    await waitFor(() => expect(input()).toBeDisabled())
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
  })
})

describe('TickerSearch load failures', () => {
  it.each([
    ['rate_limited', 'Rate-limited by the data provider — try again in a moment.'],
    ['invalid_symbol', '"ZZZ" isn\'t a recognized ticker symbol.'],
    ['no_data', 'No data is available for "ZZZ" — retrying is unlikely to help.'],
  ])('has its own message for %s, as an alert, keeping the typed value and selecting nothing', async (status, message) => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status })
    const { onSelectTicker, onLoaded } = renderSearch()

    await userEvent.type(input(), 'ZZZ{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(input()).toHaveValue('ZZZ')
    expect(onSelectTicker).not.toHaveBeenCalled()
    expect(onLoaded).not.toHaveBeenCalled()
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
  })

  it('separates a non-2xx failure from a network failure', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker')
    load.mockRejectedValueOnce(new ApiError('Server error', { status: 500, body: null }))
    renderSearch()

    await userEvent.type(input(), 'ZZZ{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong loading this ticker — please try again.')

    load.mockRejectedValueOnce(new TypeError('fetch failed'))
    await userEvent.type(input(), '{Enter}')
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Network error — could not reach the server.'),
    )
  })

  it('clears an old failure when the next Enter selects a symbol that is in the Rail', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'no_data' })
    renderSearch()
    await userEvent.type(input(), 'ZZZ{Enter}')
    await screen.findByRole('alert')

    await userEvent.clear(input())
    await userEvent.type(input(), 'TCB{Enter}')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('TickerSearch invalidation', () => {
  it('invalidates the catalog, history and range of the loaded symbol, and nothing else', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })
    const queryClient = newQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    renderSearch({}, queryClient)

    await userEvent.type(input(), 'FPT{Enter}')

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([filters]) => filters.queryKey)).toEqual([
      ['tickers'],
      ['ticker-history', 'FPT'],
      ['ticker-range', 'FPT'],
    ])
  })

  it('invalidates nothing when the load does not answer ok', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'rate_limited' })
    const queryClient = newQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    renderSearch({}, queryClient)

    await userEvent.type(input(), 'FPT{Enter}')

    await screen.findByRole('alert')
    expect(invalidate).not.toHaveBeenCalled()
  })
})

describe('TickerSearch outside the phone layout', () => {
  it.each(['wide', 'collapsed', 'drawer'])('is not a combobox and opens no popup in %s mode', async (layoutMode) => {
    renderSearch({ layoutMode })

    await userEvent.type(input(), 'V')

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(input()).not.toHaveAttribute('aria-expanded')
  })
})

describe('TickerSearch as the phone combobox', () => {
  const renderPhone = (props = {}) => renderSearch({ layoutMode: 'phone', ...props })

  it('is a combobox that owns a listbox of the matches, with each row tagged in text', async () => {
    renderPhone()

    await userEvent.type(input(), 'v')

    const box = screen.getByRole('combobox', { name: /search ticker/i })
    expect(box).toHaveAttribute('aria-expanded', 'true')
    expect(box).toHaveAttribute('aria-autocomplete', 'list')
    const listbox = screen.getByRole('listbox')
    expect(box).toHaveAttribute('aria-controls', listbox.id)
    const options = within(listbox).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringMatching(/^VIB.*Loaded 30d ago.*Stale$/),
      expect.stringMatching(/^VND.*Loaded 1d ago$/),
      expect.stringMatching(/^VCB.*Loaded 2d ago$/),
    ])
  })

  it('is collapsed while the input is empty', () => {
    renderPhone()

    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('combobox')).not.toHaveAttribute('aria-controls')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('moves the active option with Down and Up, and selects it with Enter', async () => {
    const { onSelectTicker } = renderPhone()
    await userEvent.type(input(), 'V')

    await userEvent.keyboard('{ArrowDown}{ArrowDown}')
    const options = screen.getAllByRole('option')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-activedescendant', options[1].id)
    expect(options[1]).toHaveAttribute('aria-selected', 'true')

    await userEvent.keyboard('{ArrowUp}')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-activedescendant', options[0].id)

    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(onSelectTicker).toHaveBeenCalledWith('VND')
    expect(input()).toHaveValue('')
  })

  it('stays on the first and last option rather than wrapping', async () => {
    renderPhone()
    await userEvent.type(input(), 'V')
    const options = screen.getAllByRole('option')

    await userEvent.keyboard('{ArrowUp}{ArrowUp}')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-activedescendant', options[0].id)

    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-activedescendant', options[2].id)
  })

  it('selects an option when it is tapped', async () => {
    const { onSelectTicker } = renderPhone()
    await userEvent.type(input(), 'V')

    await userEvent.click(screen.getByRole('option', { name: /^VCB/ }))

    expect(onSelectTicker).toHaveBeenCalledWith('VCB')
    expect(input()).toHaveValue('')
  })

  it('closes the list on Escape and clears the input on a second Escape', async () => {
    renderPhone()
    await userEvent.type(input(), 'V')

    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(input()).toHaveValue('V')

    await userEvent.keyboard('{Escape}')
    expect(input()).toHaveValue('')
  })

  it('offers a symbol with no match as one option, "Load SYM", and Enter loads it', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'ok', rows_loaded: 1 })
    const { onSelectTicker } = renderPhone()

    await userEvent.type(input(), 'zzz')

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveTextContent('Load ZZZ')

    await userEvent.keyboard('{Enter}')
    await waitFor(() => expect(load).toHaveBeenCalledWith('ZZZ'))
    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('ZZZ'))
  })

  it('loads the symbol when the "Load SYM" option is tapped', async () => {
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ZZZ', status: 'ok', rows_loaded: 1 })
    renderPhone()
    await userEvent.type(input(), 'zzz')

    await userEvent.click(screen.getByRole('option', { name: 'Load ZZZ' }))

    await waitFor(() => expect(load).toHaveBeenCalledWith('ZZZ'))
  })

  it('announces how many tickers match, as the Rail does at wider widths', async () => {
    renderPhone()

    await userEvent.type(input(), 'V')

    expect(screen.getByText('3 of 4 tickers')).toHaveAttribute('aria-live', 'polite')
  })

  it('keeps the plain Enter behaviour with no active option: select a symbol in the list', async () => {
    const { onSelectTicker } = renderPhone()

    await userEvent.type(input(), 'tcb{Enter}')

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
  })
})
