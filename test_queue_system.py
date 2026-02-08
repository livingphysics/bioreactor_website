#!/usr/bin/env python3
"""
Test script for the Bioreactor Queue System
Tests basic queue functionality including submission, status checking, and admin controls.
"""

import requests
import time
import json
import uuid

# Configuration
HUB_URL = "http://localhost:8000"
WEB_URL = "http://localhost:3000"

def test_queue_system():
    """Test the queue system functionality"""
    print("🧪 Testing Bioreactor Queue System")
    print("=" * 50)
    
    # Generate a session ID
    session_id = str(uuid.uuid4())
    headers = {"X-Session-ID": session_id}
    
    # Test 1: Check queue status
    print("\n1. Checking initial queue status...")
    try:
        response = requests.get(f"{HUB_URL}/api/queue/status")
        if response.status_code == 200:
            queue_status = response.json()
            print(f"✅ Queue status: {queue_status['total_queued']} queued, {queue_status['total_running']} running")
        else:
            print(f"❌ Failed to get queue status: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Error getting queue status: {e}")
        return
    
    # Test 2: Submit a test experiment
    print("\n2. Submitting test experiment...")
    test_script = """
import time
print("Starting test experiment...")
time.sleep(5)  # Simulate some work
print("Test experiment completed!")
"""
    
    try:
        response = requests.post(
            f"{HUB_URL}/api/experiments/start",
            json={"script_content": test_script},
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            experiment_id = result["experiment_id"]
            queue_position = result["queue_position"]
            print(f"✅ Experiment submitted: {experiment_id}")
            print(f"   Queue position: {queue_position}")
        else:
            print(f"❌ Failed to submit experiment: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"❌ Error submitting experiment: {e}")
        return
    
    # Test 3: Check experiment status
    print("\n3. Checking experiment status...")
    try:
        response = requests.get(f"{HUB_URL}/api/experiments/{experiment_id}/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Experiment status: {status['experiment']['status']}")
        else:
            print(f"❌ Failed to get experiment status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting experiment status: {e}")
    
    # Test 4: Check updated queue status
    print("\n4. Checking updated queue status...")
    try:
        response = requests.get(f"{HUB_URL}/api/queue/status")
        if response.status_code == 200:
            queue_status = response.json()
            print(f"✅ Updated queue: {queue_status['total_queued']} queued, {queue_status['total_running']} running")
        else:
            print(f"❌ Failed to get updated queue status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting updated queue status: {e}")
    
    # Test 5: Get user experiments
    print("\n5. Getting user experiments...")
    try:
        response = requests.get(f"{HUB_URL}/api/experiments/user", headers=headers)
        if response.status_code == 200:
            user_experiments = response.json()
            print(f"✅ User has {len(user_experiments['experiments'])} experiments")
        else:
            print(f"❌ Failed to get user experiments: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting user experiments: {e}")
    
    # Test 6: Test admin controls (pause experiment)
    print("\n6. Testing admin controls (pause experiment)...")
    try:
        response = requests.post(f"{HUB_URL}/api/experiments/{experiment_id}/pause")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Experiment paused: {result['message']}")
        else:
            print(f"❌ Failed to pause experiment: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error pausing experiment: {e}")
    
    # Test 7: Resume experiment
    print("\n7. Resuming experiment...")
    try:
        response = requests.post(f"{HUB_URL}/api/experiments/{experiment_id}/resume")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Experiment resumed: {result['message']}")
        else:
            print(f"❌ Failed to resume experiment: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error resuming experiment: {e}")
    
    # Test 8: Cancel experiment
    print("\n8. Cancelling experiment...")
    try:
        response = requests.post(f"{HUB_URL}/api/experiments/{experiment_id}/cancel")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Experiment cancelled: {result['message']}")
        else:
            print(f"❌ Failed to cancel experiment: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error cancelling experiment: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Queue system test completed!")
    print("\nTo test the web interface:")
    print(f"   Web Server: {WEB_URL}")
    print(f"   Hub API: {HUB_URL}")

if __name__ == "__main__":
    test_queue_system() 
