import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PredictionDisplay } from './PredictionDisplay'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'

function renderDisplay(ticker) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <PredictionDisplay ticker={ticker} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('PredictionDisplay', () => {
  it('renders its title and an N/A placeholder when no ticker is selected (design.md Decision 13)', () => {
    renderDisplay(null)

    expect(screen.getByRole('heading', { name: 'Prediction' })).toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('keeps the same three-line shape (percent/as-of/horizon) with no ticker selected, so selecting one causes no layout jump', () => {
    renderDisplay(null)

    expect(screen.getByText('N/A')).toBeInTheDocument()
    expect(screen.getByText('As of —')).toBeInTheDocument()
    expect(screen.getByText('Fixed horizon: 5 trading sessions')).toBeInTheDocument()
  })

  it('shows a loading message while the prediction is in flight', () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockReturnValue(new Promise(() => {}))

    renderDisplay('TCB')

    expect(screen.getByText(/loading prediction/i)).toBeInTheDocument()
  })

  it('converts predicted_log_return to a percentage and never renders the raw value (Rule 2)', async () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: 0.02,
    })

    renderDisplay('TCB')

    const expectedPercent = ((Math.exp(0.02) - 1) * 100).toFixed(2)
    expect(await screen.findByText(`+${expectedPercent}%`)).toBeInTheDocument()
    expect(screen.getByText(/as of 2026-08-10/i)).toBeInTheDocument()
    expect(screen.getByText(/5 trading sessions/i)).toBeInTheDocument()
    // Static horizon label, never a slider/input implying an adjustable horizon.
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    expect(screen.queryByText('0.02')).not.toBeInTheDocument()
  })

  it('renders a negative move with a minus sign and down styling', async () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: -0.03,
    })

    renderDisplay('TCB')

    const expectedPercent = ((Math.exp(-0.03) - 1) * 100).toFixed(2)
    const el = await screen.findByText(`${expectedPercent}%`)
    expect(el).toBeInTheDocument()
    expect(el).toHaveAttribute('data-direction', 'down')
  })

  it('shows a distinct near_gap message with no percentage figure', async () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'near_gap',
    })

    renderDisplay('TCB')

    expect(await screen.findByText(/data gap/i)).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('shows a distinct not-loaded message for a 404 response', async () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockRejectedValue(
      new ApiError('Ticker has not been loaded', { status: 404 }),
    )

    renderDisplay('VIB')

    expect(await screen.findByText(/hasn't been loaded yet/i)).toBeInTheDocument()
  })

  it('shows a distinct feature-computation-failure message for a 5xx response', async () => {
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockRejectedValue(
      new ApiError('Feature computation failed', { status: 503 }),
    )

    renderDisplay('TCB')

    const message = await screen.findByText(/feature computation failed/i)
    expect(message).toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded yet/i)).not.toBeInTheDocument()
  })

  it('keeps the 404, 5xx, and near_gap states visually distinct from one another', async () => {
    const cases = [
      { setup: () => new ApiError('not found', { status: 404 }), rejects: true, text: /hasn't been loaded yet/i },
      { setup: () => new ApiError('failed', { status: 503 }), rejects: true, text: /feature computation failed/i },
      { setup: () => ({ ticker: 'TCB', as_of: '2026-08-10', status: 'near_gap' }), rejects: false, text: /data gap/i },
    ]

    for (const testCase of cases) {
      vi.restoreAllMocks()
      const spy = vi.spyOn(tickersApi, 'fetchTickerPrediction')
      if (testCase.rejects) {
        spy.mockRejectedValue(testCase.setup())
      } else {
        spy.mockResolvedValue(testCase.setup())
      }
      const { unmount } = renderDisplay('TCB')
      expect(await screen.findByText(testCase.text)).toBeInTheDocument()
      unmount()
    }
  })
})
