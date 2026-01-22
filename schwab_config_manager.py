"""
Configuration Management for Schwab 0DTE Options Trading Bot
Handles OAuth credentials securely and manages strategy parameters
"""

import os
import json
import logging
import webbrowser
import secrets
import hashlib
import base64
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import threading
import keyring
from cryptography.fernet import Fernet
import yaml

logger = logging.getLogger(__name__)


@dataclass
class SchwabCredentials:
    """Secure storage of Schwab OAuth credentials"""
    client_id: str
    client_secret: str
    refresh_token: str
    redirect_uri: str = "https://127.0.0.1:8182/callback"


@dataclass
class OptionsStrategyParameters:
    """0DTE Options trading strategy parameters - slippage-aware defaults"""
    # Timing parameters
    time_window_seconds: int = 14
    min_price_movement_dollars: float = 0.50

    # Options selection - tuned for slippage
    target_delta: float = 0.45  # Higher delta = higher premium = spread less impactful
    max_bid_ask_spread_percent: float = 0.08  # Tighter requirement
    min_option_price: float = 1.50  # Minimum premium (spread less % impact)
    min_volume: int = 500  # Liquidity filter
    min_open_interest: int = 1000  # Liquidity filter

    # Risk management - widened for slippage reality
    max_positions: int = 1
    stop_loss_percent: float = 35.0  # Wider to avoid slippage-triggered stops
    take_profit_percent: float = 60.0  # Higher target to overcome spread costs

    # Slippage-aware order settings
    use_aggressive_limit: bool = True
    limit_offset_cents: float = 0.02  # Offset above ask for buys
    order_timeout_seconds: float = 3.0
    max_chase_attempts: int = 3
    chase_increment_cents: float = 0.03

    # Time filters - earlier cutoff to avoid spread widening
    no_trade_before: str = "09:45"
    no_trade_after: str = "15:00"  # Earlier (was 15:30)
    force_close_time: str = "15:50"

    # Position sizing
    contracts_per_signal: int = 1
    max_contracts: int = 10
    max_daily_loss_dollars: float = 500.0
    max_daily_trades: int = 10

    # Performance optimization
    polling_interval_ms: int = 50
    order_timeout_ms: int = 3000


@dataclass
class UnderlyingConfig:
    """Configuration for the underlying asset"""
    symbol: str = "SPY"
    min_option_volume: int = 100
    min_open_interest: int = 500

    # SPY-specific
    market_open: str = "09:30"
    market_close: str = "16:00"


# Predefined strategy presets - all tuned for slippage reality
STRATEGY_PRESETS = {
    "conservative": OptionsStrategyParameters(
        time_window_seconds=20,
        min_price_movement_dollars=0.75,
        target_delta=0.40,
        max_bid_ask_spread_percent=0.06,  # Very tight spread requirement
        min_option_price=2.00,  # Higher premium = less slippage impact
        min_volume=1000,
        min_open_interest=2000,
        stop_loss_percent=25.0,
        take_profit_percent=40.0,
        max_daily_loss_dollars=300.0,
        max_daily_trades=5,
        no_trade_after="14:30"  # Very early cutoff
    ),
    "moderate": OptionsStrategyParameters(
        time_window_seconds=14,
        min_price_movement_dollars=0.50,
        target_delta=0.45,
        max_bid_ask_spread_percent=0.08,
        min_option_price=1.50,
        min_volume=500,
        min_open_interest=1000,
        stop_loss_percent=35.0,
        take_profit_percent=60.0,
        max_daily_loss_dollars=500.0,
        max_daily_trades=10,
        no_trade_after="15:00"
    ),
    "aggressive": OptionsStrategyParameters(
        time_window_seconds=10,
        min_price_movement_dollars=0.35,
        target_delta=0.50,
        max_bid_ask_spread_percent=0.10,
        min_option_price=1.00,
        min_volume=300,
        min_open_interest=500,
        stop_loss_percent=45.0,
        take_profit_percent=80.0,
        max_daily_loss_dollars=1000.0,
        max_daily_trades=20,
        no_trade_after="15:15"
    )
}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callback"""

    def do_GET(self):
        """Handle the OAuth callback"""
        query = urlparse(self.path).query
        params = parse_qs(query)

        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response = b"""
            <html>
            <body style="font-family: Arial; text-align: center; padding-top: 50px;">
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(response)
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error = params.get('error', ['Unknown error'])[0]
            self.wfile.write(f"<html><body>Error: {error}</body></html>".encode())

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


class SchwabConfigManager:
    """Manages configuration and OAuth credentials securely"""

    def __init__(self, config_dir: str = "~/.schwab_0dte_bot"):
        self.config_dir = Path(config_dir).expanduser()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.config_file = self.config_dir / "config.yaml"
        self.credentials_file = self.config_dir / ".credentials.enc"
        self.key_file = self.config_dir / ".key"

        self._ensure_encryption_key()

    def _ensure_encryption_key(self):
        """Create or load encryption key"""
        if not self.key_file.exists():
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            self.key_file.chmod(0o600)

        self.cipher = Fernet(self.key_file.read_bytes())

    def save_credentials(self, credentials: SchwabCredentials):
        """Save encrypted credentials"""
        try:
            cred_json = json.dumps(asdict(credentials))
            encrypted = self.cipher.encrypt(cred_json.encode())
            self.credentials_file.write_bytes(encrypted)
            self.credentials_file.chmod(0o600)
            logger.info("Schwab credentials saved securely")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            raise

    def load_credentials(self) -> Optional[SchwabCredentials]:
        """Load and decrypt credentials"""
        try:
            if not self.credentials_file.exists():
                return None

            encrypted = self.credentials_file.read_bytes()
            decrypted = self.cipher.decrypt(encrypted)
            cred_dict = json.loads(decrypted.decode())

            return SchwabCredentials(**cred_dict)
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def save_credentials_to_keyring(self, credentials: SchwabCredentials):
        """Alternative: Save credentials to system keyring"""
        keyring.set_password("schwab_0dte_bot", "client_id", credentials.client_id)
        keyring.set_password("schwab_0dte_bot", "client_secret", credentials.client_secret)
        keyring.set_password("schwab_0dte_bot", "refresh_token", credentials.refresh_token)
        keyring.set_password("schwab_0dte_bot", "redirect_uri", credentials.redirect_uri)
        logger.info("Credentials saved to system keyring")

    def load_credentials_from_keyring(self) -> Optional[SchwabCredentials]:
        """Load credentials from system keyring"""
        try:
            client_id = keyring.get_password("schwab_0dte_bot", "client_id")
            if not client_id:
                return None

            return SchwabCredentials(
                client_id=client_id,
                client_secret=keyring.get_password("schwab_0dte_bot", "client_secret"),
                refresh_token=keyring.get_password("schwab_0dte_bot", "refresh_token"),
                redirect_uri=keyring.get_password("schwab_0dte_bot", "redirect_uri") or "https://127.0.0.1:8182/callback"
            )
        except Exception:
            return None

    def update_refresh_token(self, new_token: str, use_keyring: bool = False):
        """Update the refresh token (called when token is refreshed)"""
        if use_keyring:
            keyring.set_password("schwab_0dte_bot", "refresh_token", new_token)
        else:
            creds = self.load_credentials()
            if creds:
                creds.refresh_token = new_token
                self.save_credentials(creds)

    def save_strategy_config(self, params: OptionsStrategyParameters,
                             underlying: UnderlyingConfig,
                             environment: dict = None):
        """Save strategy configuration"""
        config = {
            "strategy": asdict(params),
            "underlying": asdict(underlying),
            "environment": environment or {
                "paper_trading": True,
                "log_level": "INFO",
                "enable_notifications": False,
                "notification_webhook": ""
            }
        }

        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Strategy configuration saved to {self.config_file}")

    def load_strategy_config(self) -> tuple[OptionsStrategyParameters, UnderlyingConfig, dict]:
        """Load strategy configuration"""
        if not self.config_file.exists():
            return OptionsStrategyParameters(), UnderlyingConfig(), {}

        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f)

        params = OptionsStrategyParameters(**config.get("strategy", {}))
        underlying = UnderlyingConfig(**config.get("underlying", {}))
        environment = config.get("environment", {})

        return params, underlying, environment

    def create_default_config(self, preset: str = "moderate"):
        """Create a default configuration file"""
        params = STRATEGY_PRESETS.get(preset, STRATEGY_PRESETS["moderate"])
        underlying = UnderlyingConfig()
        self.save_strategy_config(params, underlying)

        print(f"\nDefault configuration created at: {self.config_file}")
        print(f"Using '{preset}' strategy preset.")

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge for OAuth"""
        # Generate random code verifier (43-128 chars)
        code_verifier = secrets.token_urlsafe(32)

        # Create code challenge (SHA256 hash, base64url encoded)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')

        return code_verifier, code_challenge


def perform_oauth_flow(client_id: str, redirect_uri: str = "https://127.0.0.1:8182/callback") -> Optional[str]:
    """
    Perform OAuth authorization flow to get authorization code

    Note: Schwab requires HTTPS for callbacks. For local development,
    you may need to use their provided callback URL or set up local HTTPS.
    """
    config_mgr = SchwabConfigManager()
    code_verifier, code_challenge = config_mgr.generate_pkce_pair()

    # Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "api",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }

    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?{urlencode(auth_params)}"

    print("\n" + "="*60)
    print("SCHWAB OAUTH AUTHORIZATION")
    print("="*60)
    print("\nOpening browser for Schwab authorization...")
    print("\nIf browser doesn't open, visit this URL manually:")
    print(f"\n{auth_url}\n")

    # Try to open browser
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("\nAfter authorizing, you'll be redirected.")
    print("Copy the FULL redirect URL from your browser and paste it here.")
    print("\n(The URL will look like: https://127.0.0.1:8182/callback?code=...)")

    callback_url = input("\nPaste redirect URL here: ").strip()

    # Extract authorization code
    try:
        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)

        if 'code' in params:
            auth_code = params['code'][0]
            print("\nAuthorization code captured successfully!")
            return auth_code, code_verifier
        else:
            print(f"\nError: No authorization code found in URL")
            if 'error' in params:
                print(f"Error: {params['error'][0]}")
            return None, None
    except Exception as e:
        print(f"\nError parsing callback URL: {e}")
        return None, None


async def exchange_code_for_tokens(client_id: str, client_secret: str,
                                    auth_code: str, code_verifier: str,
                                    redirect_uri: str) -> Optional[dict]:
    """Exchange authorization code for access and refresh tokens"""
    import aiohttp

    auth_string = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.schwabapi.com/v1/oauth/token",
            headers=headers,
            data=data
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error = await resp.text()
                print(f"Token exchange failed: {error}")
                return None


def setup_credentials_interactive():
    """Interactive setup for Schwab OAuth credentials"""
    import asyncio

    print("\n" + "="*60)
    print("  SCHWAB 0DTE OPTIONS BOT - SETUP WIZARD")
    print("="*60)

    print("\n📋 PREREQUISITES:")
    print("   1. A Schwab brokerage account with options approval")
    print("   2. A registered app at developer.schwab.com")
    print("   3. Your app's Client ID and Client Secret")

    print("\n" + "-"*60)
    print("STEP 1: Enter your Schwab API credentials")
    print("-"*60)

    client_id = input("\nClient ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    redirect_uri = input("Redirect URI (press Enter for default): ").strip()

    if not redirect_uri:
        redirect_uri = "https://127.0.0.1:8182/callback"

    print("\n" + "-"*60)
    print("STEP 2: OAuth Authorization")
    print("-"*60)

    auth_code, code_verifier = perform_oauth_flow(client_id, redirect_uri)

    if not auth_code:
        print("\n❌ Authorization failed. Please try again.")
        return

    print("\n" + "-"*60)
    print("STEP 3: Exchanging code for tokens...")
    print("-"*60)

    # Exchange for tokens
    token_data = asyncio.run(exchange_code_for_tokens(
        client_id, client_secret, auth_code, code_verifier, redirect_uri
    ))

    if not token_data:
        print("\n❌ Token exchange failed. Please try again.")
        return

    refresh_token = token_data.get("refresh_token")

    if not refresh_token:
        print("\n❌ No refresh token received. Please try again.")
        return

    print("\n✅ Tokens received successfully!")

    # Create credentials object
    credentials = SchwabCredentials(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        redirect_uri=redirect_uri
    )

    print("\n" + "-"*60)
    print("STEP 4: Save credentials")
    print("-"*60)

    print("\nChoose storage method:")
    print("  1. Encrypted file (default, recommended)")
    print("  2. System keyring (macOS Keychain / Windows Credential Manager)")

    choice = input("\nSelection (1-2): ").strip() or "1"

    config_mgr = SchwabConfigManager()

    if choice == "2":
        config_mgr.save_credentials_to_keyring(credentials)
        print("\n✅ Credentials saved to system keyring")
    else:
        config_mgr.save_credentials(credentials)
        print(f"\n✅ Credentials saved to: {config_mgr.credentials_file}")

    print("\n" + "-"*60)
    print("STEP 5: Strategy configuration")
    print("-"*60)

    print("\nChoose a strategy preset:")
    print("  1. Conservative - Fewer trades, tighter stops")
    print("  2. Moderate (default) - Balanced approach")
    print("  3. Aggressive - More trades, wider targets")

    preset_choice = input("\nSelection (1-3): ").strip() or "2"

    preset_map = {"1": "conservative", "2": "moderate", "3": "aggressive"}
    preset = preset_map.get(preset_choice, "moderate")

    config_mgr.create_default_config(preset)

    print("\n" + "="*60)
    print("  SETUP COMPLETE!")
    print("="*60)

    print(f"\nConfiguration directory: {config_mgr.config_dir}")
    print(f"Config file: {config_mgr.config_file}")

    print("\n📝 NEXT STEPS:")
    print("   1. Review/edit config.yaml to customize strategy parameters")
    print("   2. Run in paper trading mode first: python schwab_0dte_main.py --paper")
    print("   3. Monitor performance before going live")

    print("\n⚠️  IMPORTANT:")
    print("   - Refresh tokens expire after 7 days of inactivity")
    print("   - Run the bot at least once per week to keep tokens fresh")
    print("   - 0DTE options are HIGH RISK - only trade what you can afford to lose")


def show_current_config():
    """Display current configuration"""
    config_mgr = SchwabConfigManager()

    print("\n" + "="*60)
    print("  CURRENT CONFIGURATION")
    print("="*60)

    # Check credentials
    creds = config_mgr.load_credentials()
    if creds:
        print(f"\n✅ Credentials: Configured (Client ID: {creds.client_id[:8]}...)")
    else:
        creds = config_mgr.load_credentials_from_keyring()
        if creds:
            print(f"\n✅ Credentials: In keyring (Client ID: {creds.client_id[:8]}...)")
        else:
            print("\n❌ Credentials: Not configured (run --setup)")

    # Show strategy config
    if config_mgr.config_file.exists():
        params, underlying, env = config_mgr.load_strategy_config()

        print(f"\n📊 Strategy Parameters:")
        print(f"   Time window: {params.time_window_seconds}s")
        print(f"   Min SPY move: ${params.min_price_movement_dollars}")
        print(f"   Target delta: {params.target_delta}")
        print(f"   Stop loss: {params.stop_loss_percent}%")
        print(f"   Take profit: {params.take_profit_percent}%")
        print(f"   Max positions: {params.max_positions}")
        print(f"   Max daily loss: ${params.max_daily_loss_dollars}")

        print(f"\n📈 Underlying: {underlying.symbol}")
        print(f"   Trading hours: {params.no_trade_before} - {params.no_trade_after}")
        print(f"   Force close: {params.force_close_time}")

        print(f"\n🔧 Environment:")
        print(f"   Paper trading: {env.get('paper_trading', True)}")
        print(f"   Log level: {env.get('log_level', 'INFO')}")
    else:
        print("\n❌ Config file not found (run --setup)")

    print(f"\n📁 Config directory: {config_mgr.config_dir}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        show_current_config()
    else:
        setup_credentials_interactive()
