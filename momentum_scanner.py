#!/usr/bin/env python3
"""
Pre-Market Momentum Scanner
Finds high-momentum gap stocks à la Ross Cameron / Warrior Trading style.

Sources:
  1. Schwab API movers endpoint (NASDAQ + NYSE top % gainers)
  2. Schwab quotes for pre-market price data
  3. Optional: manual ticker list from Trading Terminal

Filters:
  - Pre-market gap > threshold (default 4%)
  - Price in sweet spot for small accounts ($2–$30)
  - Volume spike vs 10-day average
  - Float < threshold (lower float = bigger moves)
"""

import asyncio
import aiohttp
import logging
import re
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class ScannerConfig:
    """Configuration for the momentum scanner"""
    # Price filters
    min_price: float = 2.00
    max_price: float = 30.00

    # Gap filters
    min_gap_percent: float = 4.0       # Minimum pre-market gap %
    min_relative_volume: float = 2.0   # Volume must be 2x+ average

    # Float filter (if available)
    max_float_millions: float = 50.0   # Prefer low float

    # Results
    max_watchlist_size: int = 5        # Top N tickers to return
    min_candidates: int = 1            # Minimum viable candidates

    # Schwab API
    api_base: str = "https://api.schwabapi.com"

    # Catalyst / News
    check_catalysts: bool = True           # Fetch news headlines per candidate
    catalyst_score_boost: float = 2.0      # 2x score multiplier if catalyst found
    no_catalyst_penalty: float = 0.4       # 0.4x score if no catalyst (gap may fade)
    catalyst_lookback_hours: int = 24      # News must be within last 24h
    catalyst_keywords: List[str] = None    # Keywords that signal a strong catalyst

    # Scan timing
    premarket_scan_start: str = "07:00"   # Start scanning
    premarket_scan_end: str = "09:25"     # Final scan before open
    rescan_interval_seconds: int = 120    # Re-scan every 2 min in pre-market

    def __post_init__(self):
        if self.catalyst_keywords is None:
            self.catalyst_keywords = [
                # Biotech / FDA
                "fda", "approval", "phase 3", "phase 2", "clinical", "trial",
                "breakthrough", "drug", "therapy", "patent",
                # Earnings / Financials
                "earnings", "revenue", "beat", "guidance", "raised",
                "profit", "eps", "quarterly",
                # Deals / Corporate
                "contract", "partnership", "acquisition", "merger", "buyout",
                "deal", "agreement", "awarded",
                # Analyst
                "upgrade", "price target", "buy rating", "outperform",
                "initiated", "coverage",
                # Products / Growth
                "launch", "product", "expansion", "record", "growth",
                # Government / Regulatory
                "government", "military", "defense", "grant", "subsidy",
                # Short squeeze / Hype
                "short squeeze", "short interest", "squeeze", "reddit",
                "meme", "viral",
            ]


@dataclass
class GapCandidate:
    """A stock identified as a momentum candidate"""
    symbol: str
    price: float                    # Current/last price
    prev_close: float               # Previous close
    gap_percent: float              # Pre-market gap %
    gap_dollars: float              # Gap in dollars
    volume: int                     # Current volume
    avg_volume: int                 # Average volume (10-day)
    relative_volume: float          # volume / avg_volume
    day_high: float                 # Pre-market high
    day_low: float                  # Pre-market low
    float_shares: Optional[float] = None    # Float in millions (if available)
    catalyst: Optional[str] = None          # News catalyst (if available)
    score: float = 0.0                      # Composite ranking score
    source: str = "schwab"                  # Where we found it

    @property
    def spread_percent(self) -> float:
        """Estimated spread as % of price"""
        if self.price > 0:
            # Rough estimate: small caps have wider spreads
            if self.price < 5:
                return 0.5
            elif self.price < 10:
                return 0.3
            else:
                return 0.15
        return 1.0


class MomentumScanner:
    """
    Scans for high-momentum gap stocks before market open.

    Workflow:
    1. Pull NASDAQ + NYSE top % gainers from Schwab movers
    2. Get detailed quotes for candidates
    3. Filter by price, gap %, volume
    4. Rank by composite score (gap × relative_volume)
    5. Return top N as the day's watchlist
    """

    def __init__(self, client, config: ScannerConfig = None):
        """
        Args:
            client: SchwabClient (or subclass) with initialized session
            config: Scanner configuration
        """
        self.client = client
        self.config = config or ScannerConfig()
        self.watchlist: List[GapCandidate] = []
        self.last_scan_time: float = 0
        self.manual_tickers: List[str] = []  # From Trading Terminal

    def add_manual_tickers(self, tickers: List[str]):
        """Add tickers from Trading Terminal or manual input"""
        self.manual_tickers = [t.upper().strip() for t in tickers]
        logger.info(f"Added {len(self.manual_tickers)} manual tickers: {', '.join(self.manual_tickers)}")

    async def scan(self) -> List[GapCandidate]:
        """
        Run full scan: movers + manual tickers → filter → rank → watchlist
        """
        logger.info("=" * 50)
        logger.info("  🔍 MOMENTUM SCANNER - Pre-Market Gap Scan")
        logger.info("=" * 50)

        candidates = []

        # 1. Schwab movers (NASDAQ + NYSE top gainers)
        try:
            mover_candidates = await self._scan_schwab_movers()
            candidates.extend(mover_candidates)
            logger.info(f"Schwab movers: {len(mover_candidates)} candidates")
        except Exception as e:
            logger.error(f"Schwab movers scan failed: {e}")

        # 2. Manual tickers (from Trading Terminal)
        if self.manual_tickers:
            try:
                manual_candidates = await self._scan_manual_tickers()
                # Merge, avoiding duplicates
                existing = {c.symbol for c in candidates}
                for mc in manual_candidates:
                    if mc.symbol not in existing:
                        candidates.append(mc)
                logger.info(f"Manual tickers: {len(manual_candidates)} candidates")
            except Exception as e:
                logger.error(f"Manual ticker scan failed: {e}")

        if not candidates:
            logger.warning("No candidates found. Market may be quiet today.")
            return []

        # 3. Filter
        filtered = self._filter_candidates(candidates)
        logger.info(f"After filtering: {len(filtered)} candidates (from {len(candidates)})")

        # 4. Check news catalysts
        if self.config.check_catalysts and filtered:
            await self._check_catalysts(filtered)
            with_catalyst = [c for c in filtered if c.catalyst]
            logger.info(f"Catalysts found: {len(with_catalyst)}/{len(filtered)} candidates have news")

        # 5. Rank (catalyst-aware scoring)
        ranked = self._rank_candidates(filtered)

        # 6. Top N
        self.watchlist = ranked[:self.config.max_watchlist_size]
        self.last_scan_time = time.time()

        # Log results
        logger.info("")
        logger.info(f"📋 TODAY'S WATCHLIST ({len(self.watchlist)} stocks):")
        logger.info("-" * 80)
        for i, c in enumerate(self.watchlist, 1):
            rv_str = f"{c.relative_volume:.1f}x" if c.relative_volume > 0 else "N/A"
            cat_str = f"📰 {c.catalyst[:50]}" if c.catalyst else "⚠️  No catalyst"
            logger.info(
                f"  {i}. {c.symbol:6s} | ${c.price:7.2f} | "
                f"Gap: +{c.gap_percent:.1f}% | "
                f"Vol: {c.volume:>10,} ({rv_str}) | "
                f"Score: {c.score:.1f}"
            )
            logger.info(f"     {cat_str}")
        logger.info("-" * 80)

        return self.watchlist

    async def _scan_schwab_movers(self) -> List[GapCandidate]:
        """Get top gainers from Schwab movers endpoint"""
        await self.client._ensure_valid_token()

        headers = {"Authorization": f"Bearer {self.client.access_token}"}
        candidates = []

        # Scan both NASDAQ and NYSE
        for index in ["$COMPX", "$NYSE", "$SPX"]:
            url = f"{self.config.api_base}/marketdata/v1/movers/{index}"
            params = {
                "sort": "PERCENT_CHANGE_UP",
                "frequency": 0  # All
            }

            try:
                async with self.client.session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        screeners = data.get("screeners", [])

                        for item in screeners:
                            symbol = item.get("symbol", "")
                            last_price = float(item.get("lastPrice", 0))
                            net_change = float(item.get("netChange", 0))
                            net_pct = float(item.get("netPercentChangeInDouble",
                                           item.get("netPercentChange", 0)))
                            total_vol = int(item.get("totalVolume", 0))

                            if last_price <= 0:
                                continue

                            prev_close = last_price - net_change if net_change else last_price

                            candidates.append(GapCandidate(
                                symbol=symbol,
                                price=last_price,
                                prev_close=prev_close,
                                gap_percent=abs(net_pct),
                                gap_dollars=abs(net_change),
                                volume=total_vol,
                                avg_volume=0,  # Will enrich later
                                relative_volume=0.0,
                                day_high=last_price,
                                day_low=last_price,
                                source=f"schwab-{index}"
                            ))

                    elif resp.status == 404:
                        logger.debug(f"Movers endpoint not available for {index}")
                    else:
                        text = await resp.text()
                        logger.warning(f"Movers {index} returned {resp.status}: {text[:200]}")

            except Exception as e:
                logger.error(f"Error scanning movers for {index}: {e}")

        # Enrich with detailed quotes (volume, highs, lows)
        if candidates:
            candidates = await self._enrich_candidates(candidates)

        return candidates

    async def _scan_manual_tickers(self) -> List[GapCandidate]:
        """Get quotes for manually-supplied tickers (from Trading Terminal)"""
        if not self.manual_tickers:
            return []

        await self.client._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.client.access_token}"}

        url = f"{self.config.api_base}/marketdata/v1/quotes"
        params = {
            "symbols": ",".join(self.manual_tickers),
            "indicative": "true"  # Include pre-market
        }

        candidates = []

        try:
            async with self.client.session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    for symbol in self.manual_tickers:
                        if symbol not in data:
                            continue

                        quote = data[symbol].get("quote", {})
                        ref = data[symbol].get("reference", {})

                        last_price = float(quote.get("lastPrice", 0))
                        prev_close = float(quote.get("closePrice", 0))

                        if last_price <= 0 or prev_close <= 0:
                            continue

                        gap_pct = ((last_price - prev_close) / prev_close) * 100
                        gap_dollars = last_price - prev_close
                        total_vol = int(quote.get("totalVolume", 0))
                        avg_vol = int(quote.get("averageVolume", ref.get("averageVolume10Days", 0)))

                        rv = total_vol / avg_vol if avg_vol > 0 else 0.0

                        candidates.append(GapCandidate(
                            symbol=symbol,
                            price=last_price,
                            prev_close=prev_close,
                            gap_percent=gap_pct,
                            gap_dollars=gap_dollars,
                            volume=total_vol,
                            avg_volume=avg_vol,
                            relative_volume=rv,
                            day_high=float(quote.get("highPrice", last_price)),
                            day_low=float(quote.get("lowPrice", last_price)),
                            source="manual"
                        ))

        except Exception as e:
            logger.error(f"Error scanning manual tickers: {e}")

        return candidates

    async def _enrich_candidates(self, candidates: List[GapCandidate]) -> List[GapCandidate]:
        """Enrich candidates with detailed quote data (avg volume, highs/lows)"""
        symbols = [c.symbol for c in candidates]

        # Batch quote (Schwab allows up to ~200 symbols)
        await self.client._ensure_valid_token()
        headers = {"Authorization": f"Bearer {self.client.access_token}"}

        # Chunk into batches of 50
        enriched = {c.symbol: c for c in candidates}

        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i+50]
            url = f"{self.config.api_base}/marketdata/v1/quotes"
            params = {"symbols": ",".join(chunk), "indicative": "true"}

            try:
                async with self.client.session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        for sym in chunk:
                            if sym not in data:
                                continue

                            quote = data[sym].get("quote", {})
                            ref = data[sym].get("reference", {})
                            c = enriched[sym]

                            # Update with richer data
                            avg_vol = int(quote.get("averageVolume",
                                         ref.get("averageVolume10Days", 0)))
                            c.avg_volume = avg_vol
                            c.relative_volume = c.volume / avg_vol if avg_vol > 0 else 0.0
                            c.day_high = float(quote.get("highPrice", c.price))
                            c.day_low = float(quote.get("lowPrice", c.price))

                            # Update price if extended hours data available
                            ext_price = float(quote.get("mark", 0))
                            if ext_price > 0:
                                c.price = ext_price
                                if c.prev_close > 0:
                                    c.gap_percent = ((c.price - c.prev_close) / c.prev_close) * 100
                                    c.gap_dollars = c.price - c.prev_close

            except Exception as e:
                logger.error(f"Error enriching batch: {e}")

        return list(enriched.values())

    # ── Catalyst / News Checking ──────────────────────────────────────────────

    async def _check_catalysts(self, candidates: List[GapCandidate]):
        """
        Check each candidate for recent news catalysts.
        Uses Yahoo Finance RSS and Google News as fallbacks (no API key needed).
        Updates candidate.catalyst with the headline if found.
        """
        symbols = [c.symbol for c in candidates]
        logger.info(f"🔍 Checking news catalysts for {len(symbols)} tickers...")

        # Fetch news for all candidates concurrently
        tasks = [self._fetch_news_for_symbol(c) for c in candidates]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_news_for_symbol(self, candidate: GapCandidate):
        """Fetch recent news for a single symbol from multiple sources"""
        symbol = candidate.symbol

        # Try sources in priority order
        sources = [
            self._fetch_yahoo_news,
            self._fetch_google_news,
        ]

        for fetch_fn in sources:
            try:
                headline = await fetch_fn(symbol)
                if headline:
                    candidate.catalyst = headline
                    logger.info(f"  📰 {symbol}: {headline[:80]}")
                    return
            except Exception as e:
                logger.debug(f"  News source failed for {symbol}: {e}")
                continue

        logger.debug(f"  ⚠️  {symbol}: No catalyst found")

    async def _fetch_yahoo_news(self, symbol: str) -> Optional[str]:
        """
        Fetch latest news headline from Yahoo Finance.
        Uses the RSS feed (no API key required).
        """
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None

                text = await resp.text()

                # Parse RSS XML for items
                # Simple regex parsing to avoid xml dependency
                items = re.findall(
                    r'<item>.*?<title><!\[CDATA\[(.*?)\]\]></title>.*?<pubDate>(.*?)</pubDate>',
                    text, re.DOTALL
                )

                if not items:
                    # Try without CDATA wrapper
                    items = re.findall(
                        r'<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>',
                        text, re.DOTALL
                    )

                if not items:
                    return None

                # Check recency and keyword match
                cutoff = datetime.utcnow() - timedelta(hours=self.config.catalyst_lookback_hours)

                for title, pub_date in items:
                    title = title.strip()

                    # Check if headline contains catalyst keywords
                    title_lower = title.lower()
                    has_keyword = any(kw in title_lower for kw in self.config.catalyst_keywords)

                    if has_keyword:
                        return title

                # If no keyword match, return most recent headline anyway
                # (the gap itself is unusual and any news is worth noting)
                if items:
                    return items[0][0].strip()

        return None

    async def _fetch_google_news(self, symbol: str) -> Optional[str]:
        """
        Fetch latest news from Google News RSS (fallback).
        """
        # URL-encode the query
        query = f"{symbol}+stock"
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=5),
                headers={"User-Agent": "Mozilla/5.0"}
            ) as resp:
                if resp.status != 200:
                    return None

                text = await resp.text()

                # Parse RSS
                items = re.findall(
                    r'<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>',
                    text, re.DOTALL
                )

                if not items:
                    return None

                # Return first headline that mentions the symbol
                for title, pub_date in items[:5]:
                    title = title.strip()
                    # Clean HTML entities
                    title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                    title = title.replace("&#39;", "'").replace("&quot;", '"')

                    if symbol.upper() in title.upper():
                        return title

                # Return first headline even if symbol not in title
                if items:
                    title = items[0][0].strip()
                    title = title.replace("&amp;", "&").replace("&#39;", "'")
                    return title

        return None

    # ── Filtering ──────────────────────────────────────────────────────────────

    def _filter_candidates(self, candidates: List[GapCandidate]) -> List[GapCandidate]:
        """Apply hard filters"""
        filtered = []

        for c in candidates:
            # Price range
            if c.price < self.config.min_price:
                logger.debug(f"  SKIP {c.symbol}: price ${c.price:.2f} < ${self.config.min_price}")
                continue
            if c.price > self.config.max_price:
                logger.debug(f"  SKIP {c.symbol}: price ${c.price:.2f} > ${self.config.max_price}")
                continue

            # Gap threshold
            if c.gap_percent < self.config.min_gap_percent:
                logger.debug(f"  SKIP {c.symbol}: gap {c.gap_percent:.1f}% < {self.config.min_gap_percent}%")
                continue

            # Relative volume (if we have data)
            if c.relative_volume > 0 and c.relative_volume < self.config.min_relative_volume:
                logger.debug(f"  SKIP {c.symbol}: rvol {c.relative_volume:.1f}x < {self.config.min_relative_volume}x")
                continue

            # Float filter (if data available)
            if c.float_shares and c.float_shares > self.config.max_float_millions:
                logger.debug(f"  SKIP {c.symbol}: float {c.float_shares:.0f}M > {self.config.max_float_millions}M")
                continue

            filtered.append(c)

        return filtered

    def _rank_candidates(self, candidates: List[GapCandidate]) -> List[GapCandidate]:
        """
        Rank candidates by composite score.
        Score = gap × relative_volume × price_score × catalyst_multiplier
        Higher = better momentum candidate.

        Catalyst is a major factor — Ross Cameron prioritizes stocks WITH news
        because gappers without catalysts tend to fade.
        """
        for c in candidates:
            # Gap component (bigger gap = more attention)
            gap_score = min(c.gap_percent, 30.0)  # Cap at 30%

            # Volume component (more volume = more liquid, more interest)
            vol_score = min(c.relative_volume, 10.0) if c.relative_volume > 0 else 2.0

            # Price sweet spot bonus ($5-$20 is ideal for small accounts)
            if 5.0 <= c.price <= 20.0:
                price_score = 2.0
            elif 2.0 <= c.price <= 5.0 or 20.0 < c.price <= 30.0:
                price_score = 1.5
            else:
                price_score = 1.0

            # Manual ticker bonus (you picked it from Trading Terminal for a reason)
            manual_bonus = 1.5 if c.source == "manual" else 1.0

            # ── CATALYST MULTIPLIER ──
            # This is the Ross Cameron edge: gaps WITH news run, gaps WITHOUT fade
            if c.catalyst:
                # Check if headline has strong catalyst keywords
                catalyst_lower = c.catalyst.lower()
                strong_keywords = ["fda", "approval", "earnings", "beat", "contract",
                                   "acquisition", "merger", "upgrade", "squeeze"]
                has_strong = any(kw in catalyst_lower for kw in strong_keywords)

                if has_strong:
                    catalyst_mult = self.config.catalyst_score_boost  # 2.0x for strong catalyst
                else:
                    catalyst_mult = 1.5  # 1.5x for any news
            else:
                catalyst_mult = self.config.no_catalyst_penalty  # 0.4x — gap likely to fade

            c.score = gap_score * vol_score * price_score * manual_bonus * catalyst_mult

        # Sort descending by score
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

    def get_watchlist_symbols(self) -> List[str]:
        """Get just the symbols from current watchlist"""
        return [c.symbol for c in self.watchlist]

    def get_premarket_highs(self) -> Dict[str, float]:
        """Get pre-market high prices for entry signal (breakout of PM high)"""
        return {c.symbol: c.day_high for c in self.watchlist}
