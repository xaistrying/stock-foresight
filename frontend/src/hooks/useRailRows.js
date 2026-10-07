import { useMemo } from 'react'
import { useTickers } from './useTickers'
import { buildRailRows } from '../lib/railRows'

/**
 * The Rail's rows from the one shared `GET /tickers` entry (React Query de-duplicates it, so the
 * Rail and the topbar search together cost one request). `allRows` ignores the search text: it is
 * what Enter may select, and the denominator of the "N of M tickers" count.
 */
export function useRailRows({ searched, sort = 'symbol', query = '' }) {
  const { data, isLoading, isError } = useTickers()
  const catalog = data?.tickers

  const rows = useMemo(() => buildRailRows({ catalog, searched, sort, query }), [catalog, searched, sort, query])
  const allRows = useMemo(() => buildRailRows({ catalog, searched }), [catalog, searched])

  return { rows, allRows, isLoading, isError }
}
