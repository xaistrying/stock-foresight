import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as tickersApi from './api/tickers'
import { catalogEntry, renderWithQuery } from './test/railFixtures'
import { resetViewport, setViewport } from './test/viewport'

// The 768 to 1143 px layout: the Rail is a non-modal drawer opened from the topbar "Tickers"
// button, so the one topbar search stays usable while it is open (design.md Decision 2).
const TICKERS = [catalogEntry('TCB'), catalogEntry('VIB'), catalogEntry('VND'), catalogEntry('HPG')]

function renderApp() {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: TICKERS })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
    ticker: 'TCB',
    rows: [{ date: '2026-10-06', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
  })
  vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({
    ticker: 'TCB', as_of: '2026-10-06', status: 'ok', reasons: [], sigma_daily_pct: 1.37,
    range_5s_pct: 3.2, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.75, n: 48 },
  })
  return renderWithQuery(<App />)
}

const tickersButton = () => screen.getByRole('button', { name: 'Tickers' })
const search = () => screen.getByLabelText(/search ticker/i)

beforeEach(() => {
  vi.restoreAllMocks()
  setViewport(900)
})

afterEach(resetViewport)

describe('Rail drawer (768 to 1143 px)', () => {
  it('is opened by a topbar "Tickers" button with aria-expanded and aria-controls', async () => {
    renderApp()

    const button = tickersButton()
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const drawer = document.getElementById(button.getAttribute('aria-controls'))
    expect(drawer).toBe(document.querySelector('nav'))
    expect(drawer).not.toBeVisible()

    await userEvent.click(button)

    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByRole('button', { name: /^TCB/ })).toBeVisible()
    expect(drawer).not.toHaveAttribute('aria-modal')
  })

  it('stays closed after the window is widened and narrowed again', async () => {
    const viewport = setViewport(900)
    renderApp()
    await userEvent.click(tickersButton())
    expect(tickersButton()).toHaveAttribute('aria-expanded', 'true')

    act(() => viewport.setWidth(1300))
    act(() => viewport.setWidth(900))

    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
    expect(document.querySelector('.rail-scrim')).toBeNull()
  })

  it('has no Tickers button at other widths', () => {
    setViewport(1440)
    renderApp()

    expect(screen.queryByRole('button', { name: 'Tickers' })).not.toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the button', async () => {
    renderApp()
    await userEvent.click(tickersButton())
    await screen.findByRole('button', { name: /^TCB/ })
    await userEvent.tab()

    await userEvent.keyboard('{Escape}')

    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
    expect(tickersButton()).toHaveFocus()
  })

  it('selects the chosen row, closes, and returns focus to the button', async () => {
    renderApp()
    await userEvent.click(tickersButton())

    await userEvent.click(await screen.findByRole('button', { name: /^VIB/ }))

    expect(await screen.findByRole('heading', { level: 1, name: 'VIB' })).toBeInTheDocument()
    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
    expect(tickersButton()).toHaveFocus()
  })

  it('closes on a click outside it, without being asked to move focus', async () => {
    renderApp()
    await userEvent.click(tickersButton())
    await screen.findByRole('button', { name: /^TCB/ })

    await userEvent.click(screen.getByRole('main'))

    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens when a non-empty value is typed into the search, leaving focus in the input', async () => {
    renderApp()
    await screen.findByRole('button', { name: /^TCB/, hidden: true })
    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')

    await userEvent.type(search(), 'v')

    expect(tickersButton()).toHaveAttribute('aria-expanded', 'true')
    expect(search()).toHaveFocus()
    const nav = screen.getByRole('navigation', { name: 'Tickers' })
    expect(within(nav).getAllByRole('button', { name: /^V/ })).toHaveLength(2)
  })

  it('does not block the search: typing keeps filtering the open drawer', async () => {
    renderApp()
    await userEvent.click(tickersButton())
    await screen.findByRole('button', { name: /^TCB/ })

    await userEvent.type(search(), 'hp')

    const nav = screen.getByRole('navigation', { name: 'Tickers' })
    expect(within(nav).getAllByRole('button', { name: /^[A-Z]{3}(,|$)/ })).toHaveLength(1)
    expect(within(nav).getByRole('button', { name: /^HPG/ })).toBeVisible()
    expect(search()).toHaveValue('HP')
  })

  it('Enter in the search selects a symbol from the drawer, and the drawer closes', async () => {
    renderApp()
    await screen.findByRole('button', { name: /^TCB/, hidden: true })

    await userEvent.type(search(), 'tcb{Enter}')

    expect(await screen.findByRole('heading', { level: 1, name: 'TCB' })).toBeInTheDocument()
    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('stays closed while the search is empty, and closes again when it is cleared', async () => {
    renderApp()
    await userEvent.type(search(), 'v')
    expect(tickersButton()).toHaveAttribute('aria-expanded', 'true')

    await userEvent.clear(search())

    expect(tickersButton()).toHaveAttribute('aria-expanded', 'false')
  })
})
