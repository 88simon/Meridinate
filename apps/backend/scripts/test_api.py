import requests

print("Testing multi-token wallets API endpoint...")
print("=" * 80)

try:
    response = requests.get("http://localhost:5001/api/multi-token-wallets?min_tokens=2")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ API Response successful")
        print(f"   Total multi-token wallets: {data['total']}")
        print(f"\n   Top wallets:")
        for wallet in data["wallets"][:5]:
            print(f"   - {wallet['wallet_address'][:12]}... in {wallet['token_count']} tokens")
    else:
        print(f"❌ API returned status {response.status_code}")
        print(f"   Response: {response.text}")

except requests.exceptions.ConnectionError:
    print("❌ Could not connect to Flask backend on port 5001")
    print("   Make sure the backend is running")
except Exception as e:
    print(f"❌ Error: {e}")
