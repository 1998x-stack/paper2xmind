#!/usr/bin/env python3
"""
Test runner for the paper2xmind project
"""

import subprocess
import sys
import os

def run_tests():
    """Run all tests with coverage"""
    print("🚀 Running paper2xmind tests...")
    print("=" * 50)
    
    # Change to project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run tests with coverage
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/", 
        "--cov=.",
        "--cov-report=term-missing",
        "-v"
    ]
    
    result = subprocess.run(cmd, cwd=os.getcwd())
    
    print("\n" + "=" * 50)
    if result.returncode == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    return result.returncode

def run_unit_tests():
    """Run only unit tests"""
    print("🧪 Running unit tests...")
    print("=" * 50)
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]
    
    result = subprocess.run(cmd, cwd=os.getcwd())
    
    print("\n" + "=" * 50)
    if result.returncode == 0:
        print("✅ All unit tests passed!")
    else:
        print("❌ Some unit tests failed!")
    
    return result.returncode

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--unit":
        exit(run_unit_tests())
    else:
        exit(run_tests())