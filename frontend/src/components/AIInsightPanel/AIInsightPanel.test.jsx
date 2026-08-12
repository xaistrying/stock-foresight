import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AIInsightPanel } from './AIInsightPanel'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'

function renderPanel(ticker) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AIInsightPanel ticker={ticker} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('AIInsightPanel', () => {
  it('shows an empty-state prompt when no ticker is selected', () => {
    renderPanel(null)
    expect(screen.getByText(/select a ticker to see its ai insight/i)).toBeInTheDocument()
  })

  it('shows a loading message while insight is in flight', () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockReturnValue(new Promise(() => {}))
    renderPanel('TCB')
    expect(screen.getByText(/loading ai insight/i)).toBeInTheDocument()
  })

  it('shows a distinct not-loaded message for a 404 response', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockRejectedValue(
      new ApiError('Ticker has not been loaded', { status: 404 }),
    )
    renderPanel('VIB')
    expect(await screen.findByText(/hasn't been loaded yet/i)).toBeInTheDocument()
  })

  it('shows a distinct feature-computation-failure message for a 5xx response', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockRejectedValue(
      new ApiError('Feature computation failed', { status: 503 }),
    )
    renderPanel('TCB')
    const message = await screen.findByText(/feature computation failed/i)
    expect(message).toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded yet/i)).not.toBeInTheDocument()
  })

  it('renders a real Confidence hit-rate for a trained ticker', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.82,
      confidence_basis: "Hit-rate over the ticker's most recent 60 backtested predictions.",
      sentiment_proxy: 'bullish',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderPanel('TCB')

    expect(await screen.findByText('82%')).toBeInTheDocument()
    expect(screen.getByText(/most recent 60 backtested predictions/i)).toBeInTheDocument()
    expect(screen.queryByText('N/A')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /backtest this ticker/i })).not.toBeInTheDocument()
  })

  it('shows explicit N/A with the Backtest action for a ticker with no backtest history', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'ACME',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: null,
      confidence_basis: 'No backtested predictions for this ticker yet — needs more price history to backtest.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderPanel('ACME')

    expect(await screen.findByText('N/A')).toBeInTheDocument()
    expect(screen.getByText(/needs more price history to backtest/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /backtest this ticker/i })).toBeInTheDocument()
    // N/A never substitutes a pooled/global percentage.
    expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument()
  })

  it('running the backtest shows a disabled loading state on the action without blocking the rest of the panel', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'ACME',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: null,
      confidence_basis: 'No backtested predictions for this ticker yet.',
      sentiment_proxy: 'bearish',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'down',
      note: null,
    })
    vi.spyOn(tickersApi, 'backtestTicker').mockReturnValue(new Promise(() => {}))

    const user = userEvent.setup()
    renderPanel('ACME')

    const button = await screen.findByRole('button', { name: /backtest this ticker/i })
    await user.click(button)

    expect(await screen.findByRole('button', { name: /backtesting/i })).toBeDisabled()
    // Sentiment and Advice stay rendered/interactive throughout.
    expect(screen.getByText('Bearish')).toBeInTheDocument()
    expect(screen.getByText('Signal: down')).toBeInTheDocument()
  })

  it('shows a "needs more history" note, not a generic failure, when the backtest 409s below threshold', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'ACME',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: null,
      confidence_basis: 'No backtested predictions for this ticker yet.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })
    vi.spyOn(tickersApi, 'backtestTicker').mockRejectedValue(
      new ApiError('Not enough clean, labeled price history', { status: 409 }),
    )

    const user = userEvent.setup()
    renderPanel('ACME')

    const button = await screen.findByRole('button', { name: /backtest this ticker/i })
    await user.click(button)

    expect(await screen.findByText(/needs more price history to backtest/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /backtest this ticker/i })).not.toBeInTheDocument()
  })

  it('labels Sentiment "Technical Signal" and always shows its basis inline, never Market Sentiment', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.7,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'bullish',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'up',
      note: null,
    })

    renderPanel('TCB')

    expect(await screen.findByText('Technical Signal')).toBeInTheDocument()
    expect(screen.getByText('Bullish')).toBeInTheDocument()
    expect(screen.getByText(/based on rsi, macd, ichimoku position/i)).toBeInTheDocument()
    // The label itself is never "Market Sentiment" — the phrase may still
    // appear in the basis text as a negation ("not news or market sentiment").
    expect(screen.queryByText('Market Sentiment')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /market sentiment/i })).not.toBeInTheDocument()
  })

  it('renders directional Advice with its reasoning line, never BUY or SELL', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.7,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'bullish',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'up',
      note: null,
    })

    renderPanel('TCB')

    expect(await screen.findByText(/move exceeds typical volatility to the upside/i)).toBeInTheDocument()
    expect(screen.getByText('Signal: up')).toBeInTheDocument()
    expect(screen.queryByText(/\bBUY\b/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bSELL\b/)).not.toBeInTheDocument()
  })

  it('renders HOLD with its reasoning line for a move within threshold', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.7,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderPanel('TCB')

    expect(await screen.findByText(/move is within normal volatility range/i)).toBeInTheDocument()
    expect(screen.getByText('HOLD')).toBeInTheDocument()
  })

  it('always renders the disclaimer alongside Confidence/Sentiment/Advice, with no hiding control', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.7,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderPanel('TCB')

    expect(await screen.findByText(/not a forecast, not investment advice/i)).toBeInTheDocument()
    // No toggle/checkbox/collapse control exists anywhere in the panel.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  it('does not render an Advice section for a near_gap ticker (advice_text is null)', async () => {
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'near_gap',
      confidence_score: 0.7,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: null,
      note: 'A data gap prevents a current prediction, so Advice is unavailable.',
    })

    renderPanel('TCB')

    await waitFor(() => {
      expect(screen.getByText('Technical Signal')).toBeInTheDocument()
    })
    expect(screen.queryByText('HOLD')).not.toBeInTheDocument()
    expect(screen.getByText(/advice is unavailable/i)).toBeInTheDocument()
    // Disclaimer still renders even when Advice itself is unavailable.
    expect(screen.getByText(/not a forecast, not investment advice/i)).toBeInTheDocument()
  })
})
