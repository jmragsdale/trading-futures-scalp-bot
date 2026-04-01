#!/usr/bin/env python3
"""
Test Tradovate API connection with provided credentials
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_tradovate_connection():
    """Test connection to Tradovate API"""
    
    print("🔌 Testing Tradovate API Connection...")
    print("=" * 60)
    
    # Get credentials from .env
    username = os.getenv('TRADOVATE_DEMO_USERNAME')
    password = os.getenv('TRADOVATE_DEMO_PASSWORD')
    app_id = os.getenv('TRADOVATE_DEMO_APP_ID')
    app_version = os.getenv('TRADOVATE_DEMO_APP_VERSION')
    device_id = os.getenv('TRADOVATE_DEMO_DEVICE_ID')
    cid = os.getenv('TRADOVATE_DEMO_CID')
    sec = os.getenv('TRADOVATE_DEMO_SEC')
    api_url = os.getenv('TRADOVATE_DEMO_API_URL')
    
    print(f"Username: {username}")
    print(f"App ID: {app_id}")
    print(f"API URL: {api_url}")
    print()
    
    # Step 1: Get access token
    print("📡 Step 1: Requesting access token...")
    
    auth_payload = {
        "name": username,
        "password": password,
        "appId": app_id,
        "appVersion": app_version,
        "deviceId": device_id,
        "cid": cid,
        "sec": sec
    }
    
    try:
        response = requests.post(
            f"{api_url}/auth/accesstokenrequest",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json"
            },
            json=auth_payload,
            timeout=10
        )
        
        if response.status_code == 200:
            auth_data = response.json()
            access_token = auth_data.get('accessToken')
            print(f"✅ Authentication successful!")
            print(f"Access Token: {access_token[:20]}...")
            print(f"User ID: {auth_data.get('userId')}")
            print()
            
            # Step 2: Get account info
            print("📊 Step 2: Fetching account information...")
            
            account_response = requests.get(
                f"{api_url}/account/list",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "accept": "application/json"
                },
                timeout=10
            )
            
            if account_response.status_code == 200:
                accounts = account_response.json()
                print(f"✅ Found {len(accounts)} account(s)")
                
                for account in accounts:
                    print(f"\n📈 Account Details:")
                    print(f"  - Account ID: {account.get('id')}")
                    print(f"  - Name: {account.get('name')}")
                    print(f"  - Account Type: {account.get('accountType')}")
                    print(f"  - Nickname: {account.get('nickname', 'N/A')}")
                    print(f"  - Active: {account.get('active', False)}")
                print()
                
                # Step 3: Get account balance
                account_id = accounts[0]['id']
                print("💰 Step 3: Fetching account balance...")
                
                balance_response = requests.get(
                    f"{api_url}/cashBalance/getCashBalanceSnapshot",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "accept": "application/json"
                    },
                    params={"accountId": account_id},
                    timeout=10
                )
                
                if balance_response.status_code == 200:
                    balance = balance_response.json()
                    print(f"✅ Account Balance:")
                    print(f"  - Cash Balance: ${balance.get('cashBalance', 0):,.2f}")
                    print(f"  - Real Buying Power: ${balance.get('realizedPnL', 0):,.2f}")
                    print(f"  - Margin Available: ${balance.get('marginAvailable', 0):,.2f}")
                else:
                    print(f"⚠️  Could not fetch balance: {balance_response.status_code}")
                print()
                
                # Step 4: Get available contracts
                print("📋 Step 4: Checking available contracts (MES, MNQ)...")
                
                contract_response = requests.get(
                    f"{api_url}/contract/find",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "accept": "application/json"
                    },
                    params={"name": "MES"},
                    timeout=10
                )
                
                if contract_response.status_code == 200:
                    contracts = contract_response.json()
                    print(f"✅ Found {len(contracts)} MES contract(s)")
                    for contract in contracts[:3]:  # Show first 3
                        print(f"  - {contract.get('name')} (ID: {contract.get('id')})")
                else:
                    print(f"⚠️  Could not fetch contracts: {contract_response.status_code}")
                
                print()
                print("=" * 60)
                print("✅ CONNECTION TEST SUCCESSFUL!")
                print("=" * 60)
                print()
                print("🚀 Next steps:")
                print("  1. Run: python tradovate_momentum_bot.py --demo --symbol MES")
                print("  2. Monitor logs for trading activity")
                print("  3. Test with small position sizes first")
                print()
                
                return True
                
            else:
                print(f"❌ Failed to fetch accounts: {account_response.status_code}")
                print(f"Response: {account_response.text}")
                return False
            
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_tradovate_connection()
