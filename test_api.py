#!/usr/bin/env python3
"""
Simple test script to verify the AI Fitness Planner API is working correctly.
Run this after starting the server with: python api_server.py
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    """Test the health check endpoint"""
    print("🏥 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            return True
        else:
            print(f"❌ Health check failed with status: {response.status_code}")
            return False
    except requests.ConnectionError:
        print("❌ Cannot connect to server. Make sure it's running on localhost:8000")
        return False

def test_parse_endpoint():
    """Test the natural language parsing endpoint"""
    print("\n🧠 Testing parse endpoint...")
    test_message = "25 year old female, wants to lose weight, 3 days per week"
    
    try:
        response = requests.post(f"{BASE_URL}/parse", json={
            "message": test_message
        })
        
        if response.status_code == 200:
            data = response.json()
            profile = data.get('profile', {})
            print(f"✅ Parse successful - Age: {profile.get('Age')}, Gender: {profile.get('Gender')}, Goal: {profile.get('Goal')}")
            return True
        else:
            print(f"❌ Parse failed with status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Parse test error: {e}")
        return False

def test_plan_endpoint():
    """Test the workout plan generation endpoint"""
    print("\n🏋️ Testing plan generation endpoint...")
    test_message = "28 year old male, muscle gain, gym access, 4 days per week"
    
    try:
        response = requests.post(f"{BASE_URL}/plan", json={
            "message": test_message,
            "weeks": 2,  # Shorter for testing
            "use_natural_language": True
        })
        
        if response.status_code == 200:
            data = response.json()
            plan = data.get('plan', '')
            source = data.get('source', 'unknown')
            
            # Check if plan contains exercises (not just rest days)
            if 'sets x' in plan and 'reps' in plan:
                print(f"✅ Plan generation successful using {source}")
                print(f"📝 Plan preview: {plan[:200]}...")
                return True
            else:
                print("⚠️  Plan generated but seems to contain only rest days")
                print(f"📝 Plan preview: {plan[:200]}...")
                return False
        else:
            print(f"❌ Plan generation failed with status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Plan generation test error: {e}")
        return False

def test_interactive_docs():
    """Test if interactive docs are available"""
    print("\n📚 Testing interactive documentation...")
    try:
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print("✅ Interactive docs available at http://localhost:8000/docs")
            return True
        else:
            print(f"❌ Docs endpoint failed with status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Docs test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 AI Fitness Planner API Test Suite")
    print("=" * 50)
    
    tests = [
        test_health_endpoint,
        test_parse_endpoint, 
        test_plan_endpoint,
        test_interactive_docs
    ]
    
    results = []
    for test in tests:
        results.append(test())
        time.sleep(0.5)  # Small delay between tests
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS")
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("✅ Your AI Fitness Planner API is ready for production!")
    else:
        print(f"⚠️  {passed}/{total} tests passed")
        print("❌ Please check the failed tests above")
    
    print(f"\n🚀 API Server: {BASE_URL}")
    print(f"📖 Documentation: {BASE_URL}/docs")
    print(f"🏥 Health Check: {BASE_URL}/health")

if __name__ == "__main__":
    main()
