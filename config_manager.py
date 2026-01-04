"""
Configuration Management for Tradovate Trading Bot
Handles credentials securely and manages strategy parameters
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import keyring
from cryptography.fernet import Fernet
import yaml

logger = logging.getLogger(__name__)

@dataclass
class TradovateCredentials:
    """Secure storage of Tradovate API credentials"""
    username: str
    password: str
    app_id: str
    app_version: str
    api_key: Optional[str] = None
    secret: Optional[str] = None
    device_id: Optional[str] = None

@dataclass
class StrategyParameters:
    """Trading strategy parameters"""
    # Timing parameters
    time_window_seconds: int = 14
    min_price_movement_ticks: int = 7
    
    # Risk management
    max_positions: int = 1
    risk_percent: float = 120.0
    take_profit_ticks: int = 22
    stop_loss_ticks: int = 10
    trailing_stop_ticks: int = 5
    slippage_ticks: int = 3
    
    # Position sizing
    contracts_per_signal: int = 1
    max_contracts: int = 10
    
    # Performance optimization
    tick_processing_interval_ms: int = 10
    order_timeout_ms: int = 100
    max_latency_ms: int = 50

@dataclass
class MicroFuturesContract:
    """Micro futures contract specifications"""
    symbol: str
    tick_size: float
    tick_value: float
    margin_requirement: float
    trading_hours: str
    exchange: str
    
    @property
    def point_value(self) -> float:
        """Calculate dollar value per point"""
        return self.tick_value / self.tick_size

# Predefined micro futures contracts
MICRO_FUTURES = {
    "MES": MicroFuturesContract(
        symbol="MES",
        tick_size=0.25,
        tick_value=1.25,
        margin_requirement=1320.0,  # Approximate, check with broker
        trading_hours="Sunday 6PM - Friday 5PM ET",
        exchange="CME"
    ),
    "MNQ": MicroFuturesContract(
        symbol="MNQ",
        tick_size=0.25,
        tick_value=0.50,
        margin_requirement=1760.0,
        trading_hours="Sunday 6PM - Friday 5PM ET",
        exchange="CME"
    ),
    "MYM": MicroFuturesContract(
        symbol="MYM",
        tick_size=1.0,
        tick_value=0.50,
        margin_requirement=990.0,
        trading_hours="Sunday 6PM - Friday 5PM ET",
        exchange="CBOT"
    ),
    "M2K": MicroFuturesContract(
        symbol="M2K",
        tick_size=0.10,
        tick_value=0.50,
        margin_requirement=880.0,
        trading_hours="Sunday 6PM - Friday 5PM ET",
        exchange="CME"
    ),
    "MGC": MicroFuturesContract(
        symbol="MGC",
        tick_size=0.10,
        tick_value=1.00,
        margin_requirement=1100.0,
        trading_hours="Sunday 6PM - Friday 5PM ET",
        exchange="COMEX"
    )
}

class ConfigManager:
    """Manages configuration and credentials securely"""
    
    def __init__(self, config_dir: str = "~/.tradovate_bot"):
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
            self.key_file.chmod(0o600)  # Read/write for owner only
        
        self.cipher = Fernet(self.key_file.read_bytes())
    
    def save_credentials(self, credentials: TradovateCredentials):
        """Save encrypted credentials"""
        try:
            # Convert to JSON
            cred_json = json.dumps(asdict(credentials))
            
            # Encrypt
            encrypted = self.cipher.encrypt(cred_json.encode())
            
            # Save to file
            self.credentials_file.write_bytes(encrypted)
            self.credentials_file.chmod(0o600)
            
            logger.info("Credentials saved securely")
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            raise
    
    def load_credentials(self) -> Optional[TradovateCredentials]:
        """Load and decrypt credentials"""
        try:
            if not self.credentials_file.exists():
                return None
            
            # Read encrypted data
            encrypted = self.credentials_file.read_bytes()
            
            # Decrypt
            decrypted = self.cipher.decrypt(encrypted)
            
            # Parse JSON
            cred_dict = json.loads(decrypted.decode())
            
            return TradovateCredentials(**cred_dict)
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None
    
    def save_credentials_to_keyring(self, credentials: TradovateCredentials):
        """Alternative: Save credentials to system keyring"""
        keyring.set_password("tradovate_bot", "username", credentials.username)
        keyring.set_password("tradovate_bot", "password", credentials.password)
        keyring.set_password("tradovate_bot", "app_id", credentials.app_id)
        keyring.set_password("tradovate_bot", "app_version", credentials.app_version)
        
        if credentials.api_key:
            keyring.set_password("tradovate_bot", "api_key", credentials.api_key)
        if credentials.secret:
            keyring.set_password("tradovate_bot", "secret", credentials.secret)
    
    def load_credentials_from_keyring(self) -> Optional[TradovateCredentials]:
        """Load credentials from system keyring"""
        try:
            return TradovateCredentials(
                username=keyring.get_password("tradovate_bot", "username"),
                password=keyring.get_password("tradovate_bot", "password"),
                app_id=keyring.get_password("tradovate_bot", "app_id"),
                app_version=keyring.get_password("tradovate_bot", "app_version"),
                api_key=keyring.get_password("tradovate_bot", "api_key"),
                secret=keyring.get_password("tradovate_bot", "secret")
            )
        except Exception:
            return None
    
    def save_strategy_config(self, params: StrategyParameters, contract: MicroFuturesContract):
        """Save strategy configuration"""
        config = {
            "strategy": asdict(params),
            "contract": asdict(contract),
            "environment": {
                "demo_mode": True,
                "log_level": "INFO",
                "data_feed": "websocket",
                "order_routing": "direct"
            }
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Strategy configuration saved to {self.config_file}")
    
    def load_strategy_config(self) -> tuple[StrategyParameters, MicroFuturesContract, dict]:
        """Load strategy configuration"""
        if not self.config_file.exists():
            # Return defaults
            return StrategyParameters(), MICRO_FUTURES["MES"], {}
        
        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        params = StrategyParameters(**config.get("strategy", {}))
        contract_data = config.get("contract", asdict(MICRO_FUTURES["MES"]))
        contract = MicroFuturesContract(**contract_data)
        environment = config.get("environment", {})
        
        return params, contract, environment
    
    def create_default_config(self):
        """Create a default configuration file"""
        params = StrategyParameters()
        contract = MICRO_FUTURES["MES"]
        self.save_strategy_config(params, contract)
        
        print(f"Default configuration created at: {self.config_file}")
        print("\nPlease edit the configuration file to customize your strategy.")
        print("\nAvailable micro futures contracts:")
        for symbol, spec in MICRO_FUTURES.items():
            print(f"  {symbol}: Tick Size={spec.tick_size}, "
                  f"Tick Value=${spec.tick_value}, "
                  f"Margin=${spec.margin_requirement}")

def setup_credentials_interactive():
    """Interactive setup for credentials"""
    print("\n=== Tradovate Trading Bot Setup ===\n")
    
    print("Please enter your Tradovate credentials:")
    username = input("Username: ")
    password = input("Password: ")  # Consider using getpass for security
    app_id = input("App ID: ")
    app_version = input("App Version (default: 1.0): ") or "1.0"
    
    print("\nOptional API credentials (press Enter to skip):")
    api_key = input("API Key: ") or None
    secret = input("Secret: ") or None
    
    credentials = TradovateCredentials(
        username=username,
        password=password,
        app_id=app_id,
        app_version=app_version,
        api_key=api_key,
        secret=secret
    )
    
    config_mgr = ConfigManager()
    
    print("\nChoose storage method:")
    print("1. Encrypted file (default)")
    print("2. System keyring")
    choice = input("Selection (1-2): ") or "1"
    
    if choice == "2":
        config_mgr.save_credentials_to_keyring(credentials)
        print("Credentials saved to system keyring")
    else:
        config_mgr.save_credentials(credentials)
        print("Credentials saved to encrypted file")
    
    # Create default strategy config
    config_mgr.create_default_config()
    
    print("\nSetup complete! You can now run the trading bot.")

if __name__ == "__main__":
    # Run interactive setup
    setup_credentials_interactive()
