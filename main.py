"""
Main Controller for Deriv Multi-Asset Multipliers Trading Bot
Coordinates all components and runs the trading loop across multiple assets
main.py - MULTI-ASSET WITH TOP-DOWN STRATEGY SUPPORT
"""

# Triggering new build after removing problematic binary files
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional
import config
from utils import setup_logger, print_statistics, format_currency
from data_fetcher import DataFetcher
from strategy import TradingStrategy
from trade_engine import TradeEngine
from risk_manager import RiskManager
from strategy_registry import get_strategy, normalize_strategy_name

# Setup logger
logger = setup_logger(config.LOG_FILE, config.LOG_LEVEL)

# Try to import telegram notifier
try:
    from telegram_notifier import notifier, TelegramLoggingHandler
    TELEGRAM_ENABLED = True
    
    # Attach Telegram logging handler to root logger
    if TELEGRAM_ENABLED:
        try:
            telegram_handler = TelegramLoggingHandler(notifier)
            logging.getLogger().addHandler(telegram_handler)
            logger.info("✅ Telegram error logging enabled")
        except Exception as e:
            logger.warning(f"⚠️ Failed to setup Telegram logging: {e}")
            
except ImportError:
    TELEGRAM_ENABLED = False
    logger.warning("⚠️ Telegram notifier not available")

class TradingBot:
    """Main trading bot controller with multi-asset support"""
    
    def __init__(self):
        self.running = False
        self.data_fetcher = None
        self.trade_engine = None
        self.strategy = None
        self.risk_manager = None
        self._state_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "bot_state.json"
        )
        self._last_heartbeat = datetime.now()

        # Active strategy (Conservative | Scalping | RiseFall)
        self.active_strategy = normalize_strategy_name(
            os.getenv("ACTIVE_STRATEGY", "Conservative")
        )

        # Multi-asset tracking
        self.symbols = config.get_all_symbols()
        self.asset_signals: Dict[str, Optional[Dict]] = {symbol: None for symbol in self.symbols}
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.warning("\n⚠️ Shutdown signal received")
        self.running = False
    
    async def initialize(self) -> bool:
        """
        Initialize all bot components
        
        Returns:
            True if initialization successful
        """
        try:
            logger.info("="*60)
            logger.info("🚀 Initializing Deriv Multi-Asset Multipliers Trading Bot")
            logger.info("="*60)
            
            # Validate configuration
            logger.info("📋 Validating configuration...")
            config.validate_config()
            logger.info("✅ Configuration valid")
            
            # Initialize components
            logger.info("🔧 Initializing components...")
            
            self.data_fetcher = DataFetcher(
                config.DERIV_API_TOKEN_RAW or config.DERIV_API_TOKEN,
                config.DERIV_APP_ID
            )

            self.trade_engine = TradeEngine(
                config.DERIV_API_TOKEN_RAW or config.DERIV_API_TOKEN,
                config.DERIV_APP_ID
            )

            # Strategy-aware instantiation (Conservative / Scalping / RiseFall)
            strategy_class, risk_manager_class = get_strategy(
                self.active_strategy, respect_feature_flags=True
            )
            self.strategy = strategy_class()
            self.risk_manager = risk_manager_class()

            # Scope symbols/asset config to the active strategy when available
            if hasattr(self.strategy, "get_symbols"):
                strat_symbols = self.strategy.get_symbols()
                if strat_symbols:
                    self.symbols = list(strat_symbols)
                    self.asset_signals = {s: None for s in self.symbols}
            if hasattr(self.strategy, "get_asset_config"):
                strat_assets = self.strategy.get_asset_config()
                if strat_assets:
                    self.trade_engine.configure_assets(
                        asset_configs=strat_assets,
                        blocked_symbols=getattr(self.strategy, "blocked_symbols", None),
                    )
            if hasattr(self.risk_manager, "update_risk_settings") and config.FIXED_STAKE:
                try:
                    self.risk_manager.update_risk_settings(config.FIXED_STAKE)
                except Exception as e:
                    logger.warning(f"⚠️ Could not apply fixed stake: {e}")

            # Connect to API
            logger.info("🔌 Connecting to Deriv API...")
            
            data_connected = await self.data_fetcher.connect()
            trade_connected = await self.trade_engine.connect()
            
            if not data_connected or not trade_connected:
                logger.error("❌ Failed to connect to API")
                return False
            
            # Get and log account balance
            balance = await self.data_fetcher.get_balance()
            if balance:
                logger.info(f"💰 Account Balance: {format_currency(balance)}")
                if TELEGRAM_ENABLED:
                    try:
                        strategy_mode = "Top-Down Multi-Timeframe" if config.USE_TOPDOWN_STRATEGY else "Two-Phase Scalping"
                        await notifier.notify_bot_started(balance, config.FIXED_STAKE, strategy_mode)
                    except Exception as e:
                        logger.error(f"❌ Telegram notification failed: {e}")
            
            # Log trading parameters
            logger.info("="*60)
            
            strategy_display = self.strategy.get_strategy_name() if hasattr(self.strategy, "get_strategy_name") else "Conservative"
            logger.info(f"TRADING PARAMETERS - {strategy_display.upper()}")
            logger.info("="*60)
            logger.info(f"📊 Assets Monitored: {len(self.symbols)}")
            strat_assets = {}
            if hasattr(self.strategy, "get_asset_config"):
                try:
                    strat_assets = self.strategy.get_asset_config() or {}
                except Exception:
                    strat_assets = {}
            for symbol in self.symbols:
                asset_info = strat_assets.get(symbol) or config.ASSET_CONFIG.get(symbol, {})
                mult = asset_info.get('multiplier', '?')
                desc = asset_info.get('description', symbol)
                logger.info(f"   • {symbol}: {mult}x ({desc})")
            
            stake_display = format_currency(config.FIXED_STAKE) if config.FIXED_STAKE else "USER_DEFINED"
            logger.info(f"💵 Stake: {stake_display}")
            logger.info(f"🎯 Max Concurrent Trades: {config.MAX_CONCURRENT_TRADES}")
            
            if self.active_strategy == "Scalping":
                logger.info(f"📈 Strategy: Scalping (1h/5m/1m multi-timeframe)")
                logger.info(f"🎯 Min R:R Ratio: 1:{getattr(config, 'SCALPING_MIN_RR_RATIO', 1.4)}")
                logger.info(f"💰 Dynamic TP/SL: ATR-based")
            elif config.USE_TOPDOWN_STRATEGY:
                logger.info(f"📈 Strategy: Top-Down Multi-Timeframe Analysis")
                logger.info(f"📊 Timeframes: 1w, 1d, 4h, 1h, 5m, 1m")
                logger.info(f"🎯 Min R:R Ratio: 1:{config.TOPDOWN_MIN_RR_RATIO}")
                logger.info(f"💰 Dynamic TP/SL: Based on market structure")
            else:
                tp_pct = getattr(config, 'TAKE_PROFIT_PERCENT', None)
                sl_pct = getattr(config, 'STOP_LOSS_PERCENT', None)
                if tp_pct is not None and sl_pct is not None:
                    logger.info(f"🎯 Take Profit: {tp_pct}%")
                    logger.info(f"🛑 Stop Loss: {sl_pct}%")
                else:
                    logger.info("🎯 Take Profit: Strategy-defined")
                    logger.info("🛑 Stop Loss: Strategy-defined")
            
            logger.info(f"⏰ Cooldown: {config.COOLDOWN_SECONDS}s")
            logger.info(f"🔢 Max Daily Trades: {config.MAX_TRADES_PER_DAY}")
            daily_loss_display = format_currency(config.MAX_DAILY_LOSS) if config.MAX_DAILY_LOSS else "DYNAMIC (3x Stake)"
            logger.info(f"💸 Max Daily Loss: {daily_loss_display}")
            logger.info("="*60)
            
            logger.info("✅ Bot initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def shutdown(self):
        logger.info("🛑 Shutting down bot...")
        
        try:
            if self.trade_engine and self.trade_engine.active_contract_id:
                logger.warning(f"⚠️ Active trade {self.trade_engine.active_contract_id} at shutdown - will persist for recovery")
                await self._save_state()
            else:
                try:
                    if os.path.exists(self._state_file):
                        os.remove(self._state_file)
                except Exception:
                    pass

            if self.data_fetcher:
                await self.data_fetcher.disconnect()
            
            if self.trade_engine:
                await self.trade_engine.disconnect()
            
            # Print final statistics
            if self.risk_manager:
                logger.info("\n" + "="*60)
                logger.info("FINAL STATISTICS")
                logger.info("="*60)
                stats = self.risk_manager.get_statistics()
                print_statistics(stats)
                
                if TELEGRAM_ENABLED:
                    try:
                        await notifier.notify_bot_stopped(stats)
                    except Exception as e:
                        logger.error(f"❌ Telegram notification failed: {e}")
            
            logger.info("✅ Bot shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    async def analyze_asset(self, symbol: str) -> Optional[Dict]:
        """
        Analyze a single asset and generate trading signal
        
        Args:
            symbol: Trading symbol (e.g., 'R_25')
        
        Returns:
            Signal dictionary or None if analysis failed
        """
        try:
            logger.info(f"📊 Analyzing {symbol}...")
            
            # Determine which timeframes this strategy needs
            required_tfs = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]
            if hasattr(self.strategy, "get_required_timeframes"):
                try:
                    strat_tfs = self.strategy.get_required_timeframes()
                    if strat_tfs:
                        required_tfs = list(strat_tfs)
                except Exception:
                    pass

            # Fetch data for the strategy's required timeframes
            all_timeframes = await self.data_fetcher.fetch_all_timeframes(symbol)

            if not all_timeframes:
                logger.warning(f"⚠️ Failed to fetch data for {symbol}")
                return None

            fetched_tfs = list(all_timeframes.keys())
            logger.debug(f"   Fetched timeframes: {', '.join(fetched_tfs)}")

            # Build kwargs dynamically so any strategy gets exactly the data it needs
            strategy_kwargs = {
                f"data_{tf}": all_timeframes.get(tf) for tf in required_tfs
            }
            strategy_kwargs["symbol"] = symbol
            signal = self.strategy.analyze(**strategy_kwargs)
            
            # Add symbol to signal
            if signal:
                signal['symbol'] = symbol
                asset_info = None
                if hasattr(self.strategy, "get_asset_config"):
                    try:
                        asset_info = (self.strategy.get_asset_config() or {}).get(symbol)
                    except Exception:
                        asset_info = None
                if not asset_info:
                    try:
                        asset_info = config.get_asset_info(symbol)
                    except Exception:
                        asset_info = {}
                signal['asset_info'] = asset_info
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Error analyzing {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def scan_all_assets(self) -> List[Dict]:
        """
        Scan all configured assets in parallel and return valid trading signals
        
        Returns:
            List of valid signals sorted by strength (if prioritization enabled)
        """
        logger.info(f"🔍 Scanning {len(self.symbols)} assets for trading opportunities...")
        
        # Create semaphore to limit concurrent asset analysis (prevent CPU/memory overload)
        max_concurrent = min(10, len(self.symbols))  # Max 10 concurrent analyses
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(symbol: str) -> Optional[Dict]:
            """Wrapper to analyze asset with semaphore control"""
            async with semaphore:
                return await self.analyze_asset(symbol)
        
        # Create tasks for all assets
        tasks = [analyze_with_semaphore(symbol) for symbol in self.symbols]
        
        # Execute all analyses in parallel
        logger.debug(f"⚡ Running {len(tasks)} analyses in parallel (max {max_concurrent} concurrent)...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        valid_signals = []
        for symbol, result in zip(self.symbols, results):
            # Handle exceptions
            if isinstance(result, Exception):
                logger.error(f"❌ {symbol}: Analysis failed with exception: {result}")
                self.asset_signals[symbol] = None
                continue
            
            # Store signal for tracking
            self.asset_signals[symbol] = result
            
            # Check if signal is valid for trading
            if result and result.get('can_trade'):
                valid_signals.append(result)
                logger.info(f"✅ {symbol}: Valid {result['signal']} signal (score: {result.get('score', 0)})")
            else:
                reason = result['details'].get('reason', 'Unknown') if result else 'Analysis failed'
                logger.info(f"⚪ {symbol}: {reason}")
        
        if not valid_signals:
            logger.info("📭 No valid signals found across all assets")
            return []
        
        # Prioritize by signal strength if enabled
        if config.PRIORITIZE_BY_SIGNAL_STRENGTH:
            valid_signals.sort(key=lambda s: s.get('score', 0), reverse=True)
            logger.info(f"📊 Prioritized {len(valid_signals)} signals by strength")
        
        return valid_signals
    
    async def trading_cycle(self):
        """Execute one trading cycle across all assets"""
        try:
            # Check if we can trade
            can_trade, reason = self.risk_manager.can_trade()
            
            if not can_trade:
                logger.debug(f"⏸️ Cannot trade: {reason}")
                return
            
            # Scan all assets for trading opportunities
            valid_signals = await self.scan_all_assets()
            
            if not valid_signals:
                return
            
            # Trade the first valid signal (respecting MAX_CONCURRENT_TRADES limit)
            signal = valid_signals[0]
            symbol = signal['symbol']
            
            logger.info(f"🎯 Selected {symbol} for trading (strongest signal)")
            
            # Validate trade parameters
            if config.USE_TOPDOWN_STRATEGY or self.active_strategy == "Scalping":
                # TP/SL come from the strategy signal (both top-down and scalping)
                tp_price = signal.get('take_profit')
                sl_price = signal.get('stop_loss')
                
                if not tp_price or not sl_price:
                    logger.warning(f"⚠️ {symbol}: Strategy did not provide TP/SL levels")
                    return
                
                # Validate risk/reward ratio
                entry_price = signal.get('entry_price', 0)
                if entry_price > 0:
                    rr_ratio = signal.get('risk_reward_ratio', 0)
                    # Use strategy-specific minimum RR if provided, else config default
                    min_rr = signal.get('min_rr_required')
                    if min_rr is None:
                        min_rr = config.TOPDOWN_MIN_RR_RATIO
                    if rr_ratio < min_rr:
                        logger.warning(f"⚠️ {symbol}: R:R ratio {rr_ratio:.2f} below minimum {min_rr}")
                        return
                
                valid = True
                msg = "Strategy parameters validated"
            else:
                # Legacy: Validate only stake
                if hasattr(self.risk_manager, "validate_trade_parameters"):
                    valid, msg = self.risk_manager.validate_trade_parameters(
                        stake=config.FIXED_STAKE or 50.0
                    )
                else:
                    valid, msg = True, "No stake validation for strategy"
            
            if not valid:
                logger.warning(f"⚠️ {symbol}: Invalid trade parameters: {msg}")
                return

            # ── Dynamic stake from live balance (gold-style SL formula) ──
            if getattr(config, "USE_SL_BASED_STAKE", False):
                stake = await self._compute_sl_based_stake(signal, symbol)
                if stake <= 0:
                    logger.warning(
                        f"⚠️ {symbol}: Computed stake below minimum "
                        f"({getattr(config, 'MIN_STAKE', 1.00):.2f}) - skipping trade"
                    )
                    return
                signal['stake'] = stake
                if hasattr(self.risk_manager, "update_risk_settings"):
                    try:
                        self.risk_manager.update_risk_settings(stake)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not update risk settings for stake ${stake}: {e}")
                logger.info(f"💵 Dynamic stake: ${stake:.2f} (SL-based, capital formula)")

            # Execute trade
            logger.info(f"🚀 Executing {signal['signal']} trade on {symbol}...")
            
            # Log trade details if available
            if signal.get('entry_price') is not None:
                logger.info(f"   📍 Entry: {signal.get('entry_price', 0):.4f}")
                logger.info(f"   🎯 TP: {signal.get('take_profit', 0):.4f}")
                logger.info(f"   🛡️ SL: {signal.get('stop_loss', 0):.4f}")
                logger.info(f"   📊 R:R: 1:{signal.get('risk_reward_ratio', 0):.2f}")
            
            # Execute trade with monitoring
            result = await self.trade_engine.execute_trade(signal, self.risk_manager)
            
            if result:
                # Trade completed successfully
                pnl = result.get('profit', 0.0)
                status = result.get('status', 'unknown')
                contract_id = result.get('contract_id')
                
                # Record trade closure
                self.risk_manager.record_trade_close(
                    contract_id,
                    pnl,
                    status
                )
                
                # Log statistics
                stats = self.risk_manager.get_statistics()
                logger.info(f"📈 Win Rate: {stats['win_rate']:.1f}%")
                logger.info(f"💰 Total P&L: {format_currency(stats['total_pnl'])}")
                logger.info(f"📊 Trades Today: {stats['trades_today']}/{config.MAX_TRADES_PER_DAY}")
                
                # Send Telegram notification
                if TELEGRAM_ENABLED:
                    trade_info = None
                    for t in self.risk_manager.trades_today:
                        if t.get('contract_id') == contract_id:
                            trade_info = t
                            break
                    
                    if trade_info:
                        try:
                            await notifier.notify_trade_closed(result, trade_info)
                        except Exception as e:
                            logger.error(f"❌ Telegram notification failed: {e}")
            else:
                logger.error(f"❌ {symbol}: Trade execution failed")
            
        except Exception as e:
            logger.error(f"❌ Error in trading cycle: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _compute_sl_based_stake(self, signal: dict, symbol: str) -> float:
        """
        Compute the trade stake using the gold-style SL formula with the
        live Deriv account balance as capital.
        """
        try:
            # 1. Live balance as capital (fallback to last-known on failure)
            capital = await self.data_fetcher.get_balance()
            if not capital:
                capital = getattr(self, "_last_balance", 0.0)
            if not capital or capital <= 0:
                logger.warning(f"⚠️ {symbol}: No balance available for stake formula")
                return 0.0
            self._last_balance = capital

            # 2. Per-symbol multiplier from the signal's asset info
            asset_info = signal.get('asset_info') or {}
            multiplier = asset_info.get('multiplier')
            if not multiplier:
                multiplier = getattr(config, 'MULTIPLIER', 50)
            try:
                multiplier = float(multiplier)
            except (TypeError, ValueError):
                multiplier = 50.0

            # 3. Entry/SL
            entry_price = signal.get('entry_price')
            stop_loss = signal.get('stop_loss')
            if not entry_price or not stop_loss:
                logger.warning(f"⚠️ {symbol}: Missing entry/SL for stake formula")
                return 0.0

            unit = getattr(config, 'STAKE_UNIT', 0.01)
            min_stake = getattr(config, 'MIN_STAKE', 1.00)
            from conservative_strategy.strategy import calculate_stake_from_sl

            stake = calculate_stake_from_sl(
                capital=capital,
                entry_price=entry_price,
                stop_loss=stop_loss,
                multiplier=multiplier,
                unit=unit,
                min_stake=min_stake,
            )
            logger.info(
                f"💵 Stake formula: capital=${capital:.2f}, entry={entry_price:.5f}, "
                f"SL={stop_loss:.5f}, mult={multiplier}x, unit={unit}, "
                f"min_stake=${min_stake:.2f} -> stake=${stake:.2f}"
            )
            return stake

        except Exception as e:
            logger.error(f"❌ {symbol}: Stake formula error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0.0

    async def _save_state(self):
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "active_contract_id": self.trade_engine.active_contract_id if self.trade_engine else None,
            }
            with open(self._state_file, "w") as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"❌ Failed to save state: {e}")

    async def _load_state(self):
        try:
            if not os.path.exists(self._state_file):
                return
            with open(self._state_file) as f:
                state = json.load(f)
            contract_id = state.get("active_contract_id")
            if contract_id:
                logger.warning(f"⚠️ Found open contract {contract_id} from previous session")
                if self.trade_engine:
                    status = await self.trade_engine.get_trade_status(contract_id)
                    if status and status.get("status") not in ("won", "lost", "sold"):
                        logger.warning(f"⚠️ Contract {contract_id} still appears open. Manual check recommended.")
        except Exception as e:
            logger.error(f"❌ Failed to load state: {e}")

    async def run(self):
        try:
            if not await self.initialize():
                logger.error("❌ Failed to initialize bot")
                return
            
            await self._load_state()
            
            self.running = True
            logger.info("\n🚀 Starting main trading loop")
            logger.info(f"📊 Monitoring {len(self.symbols)} assets: {', '.join(self.symbols)}")
            logger.info("Press Ctrl+C to stop\n")
            
            cycle_count = 0
            
            while self.running:
                try:
                    cycle_count += 1
                    logger.info(f"\n{'='*60}")
                    logger.info(f"CYCLE #{cycle_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info(f"{'='*60}")
                    
                    await self.trading_cycle()
                    
                    await self._save_state()

                    heartbeat_interval = 300
                    time_since_heartbeat = (datetime.now() - self._last_heartbeat).total_seconds()
                    if time_since_heartbeat >= heartbeat_interval:
                        logger.info(f"💓 Heartbeat: Bot alive | Cycle #{cycle_count} | Trades today: {self.risk_manager.total_trades if self.risk_manager else 0}")
                        self._last_heartbeat = datetime.now()
                    
                    cooldown = self.risk_manager.get_cooldown_remaining()
                    if cooldown > 0:
                        logger.info(f"⏰ Cooldown: {cooldown:.0f}s remaining")
                    
                    wait_time = max(cooldown, 30)
                    logger.info(f"⏳ Next cycle in {wait_time:.0f}s...")
                    
                    for _ in range(int(wait_time)):
                        if not self.running:
                            break
                        await asyncio.sleep(1)
                    
                except KeyboardInterrupt:
                    logger.warning("\n⚠️ Keyboard interrupt received")
                    self.running = False
                    break
                    
                except Exception as e:
                    logger.error(f"❌ Error in main loop: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(30)  # Wait before retry
            
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        finally:
            await self.shutdown()

def main():
    """Entry point"""
    try:
        # Determine strategy mode
        active_strategy = normalize_strategy_name(
            os.getenv("ACTIVE_STRATEGY", "Conservative")
        )
        if active_strategy == "Scalping":
            strategy_name = "Scalping (Multi-Timeframe)"
        elif active_strategy == "RiseFall":
            strategy_name = "Rise/Fall"
        else:
            strategy_name = "Top-Down Multi-Timeframe" if config.USE_TOPDOWN_STRATEGY else "Two-Phase Scalping"
        
        # Print welcome banner
        print("\n" + "="*60)
        print("   DERIV MULTI-ASSET MULTIPLIERS TRADING BOT")
        print(f"   {strategy_name.upper()}")
        print("="*60)
        print(f"   Version: 3.0 (Multi-Asset)")
        print(f"   Assets: {', '.join(config.get_all_symbols())}")
        print(f"   Strategy: {strategy_name}")
        print(f"   Max Concurrent: {config.MAX_CONCURRENT_TRADES}")
        if config.USE_TOPDOWN_STRATEGY:
            print(f"   Min R:R: 1:{config.TOPDOWN_MIN_RR_RATIO}")
        print("="*60 + "\n")
        
        # Create and run bot
        bot = TradingBot()
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print("\n\n✅ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
