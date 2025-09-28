#!/usr/bin/env python3
"""
Startup script for the Flask TTS application.
"""

import os
from dotenv import load_dotenv

def main():
    """Main startup function"""
    print("🎤 Flask TTS Application")
    print("=" * 30)
    
    # Load environment variables
    load_dotenv()
    
    # Check for API key
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("❌ Please set ELEVENLABS_API_KEY in your .env file")
        print("📝 Get your API key from: https://elevenlabs.io/")
        return
    
    print("✅ Starting Flask TTS Application...")
    print("📱 Web interface: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop")
    print("=" * 30)
    
    # Import and run the Flask app
    try:
        from app import app
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
