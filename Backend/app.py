from flask import Flask, request, jsonify, render_template_string
import os
import glob
import time
from dotenv import load_dotenv
from components.tts import TTSService
from components.audio_player import get_audio_player

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize TTS service
try:
    tts_service = TTSService()
    print("TTS Service initialized successfully")
except ValueError as e:
    print(f"TTS Service initialization failed: {e}")
    tts_service = None

# Initialize audio player
audio_player = get_audio_player()

# Global queue for managing text input
text_queue = []

@app.route("/")
def home():
    """Simple HTML interface for testing TTS"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>TTS Queue Manager</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            textarea { width: 100%; height: 100px; margin: 10px 0; }
            button { padding: 10px 20px; margin: 5px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .status { margin: 20px 0; padding: 10px; background: #f8f9fa; border-radius: 4px; }
            .queue-item { padding: 5px; margin: 2px 0; background: #e9ecef; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Text-to-Speech Queue Manager</h1>
            
            <div class="status">
                <h3>Status</h3>
                <p id="status">TTS Service: <span id="tts-status">Loading...</span></p>
                <p>Queue Length: <span id="queue-length">0</span></p>
            </div>
            
            <h3>Add Text to Queue</h3>
            <textarea id="textInput" placeholder="Enter text to convert to speech..."></textarea>
            <br>
            <button onclick="addToQueue()">Add to Queue</button>
            <button onclick="addMultiple()">Add Multiple Sentences</button>
            
            <h3>Queue Management</h3>
            <button onclick="playQueue()">Process Queue (Save Audio)</button>
            <button onclick="clearQueue()">Clear Queue</button>
            <button onclick="getStatus()">Refresh Status</button>
            
            <h3>Current Queue</h3>
            <div id="queueDisplay"></div>
            
            <h3>Generated Audio Files</h3>
            <button onclick="listAudioFiles()">Refresh Audio Files</button>
            <button onclick="clearAudioFiles()">Clear Audio Files</button>
            <div id="audioFilesDisplay"></div>
            
            <h3>Audio Playback</h3>
            <button onclick="playAllAudio()" style="background: #28a745; color: white; padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin: 5px;">🎵 Play All Audio Files</button>
            <button onclick="stopAudio()" style="background: #dc3545; color: white; padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin: 5px;">⏹️ Stop Playback</button>
            <button onclick="getPlaybackStatus()" style="background: #17a2b8; color: white; padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin: 5px;">📊 Check Status</button>
            <button onclick="generateAndPlay()" style="background: #6f42c1; color: white; padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin: 5px;">🎲 Generate & Play Random</button>
            <div id="playbackStatus" style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 4px; border-left: 4px solid #007bff;"></div>
        </div>
        
        <script>
            function addToQueue() {
                const text = document.getElementById('textInput').value.trim();
                if (!text) return;
                
                fetch('/api/add-text', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: text})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('textInput').value = '';
                        getStatus();
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function addMultiple() {
                const text = document.getElementById('textInput').value.trim();
                if (!text) return;
                
                const sentences = text.split('.').filter(s => s.trim());
                sentences.forEach(sentence => {
                    if (sentence.trim()) {
                        fetch('/api/add-text', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({text: sentence.trim() + '.'})
                        });
                    }
                });
                document.getElementById('textInput').value = '';
                setTimeout(getStatus, 100);
            }
            
            function playQueue() {
                fetch('/api/play-queue', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Queue processing started - audio files will be saved');
                        getStatus();
                        // Refresh audio files after a short delay
                        setTimeout(listAudioFiles, 2000);
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function clearQueue() {
                fetch('/api/clear-queue', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        getStatus();
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function getStatus() {
                fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('tts-status').textContent = data.tts_available ? 'Available' : 'Unavailable';
                    document.getElementById('queue-length').textContent = data.queue_length;
                    
                    const queueDisplay = document.getElementById('queueDisplay');
                    queueDisplay.innerHTML = '';
                    data.queue.forEach((item, index) => {
                        const div = document.createElement('div');
                        div.className = 'queue-item';
                        div.textContent = `${index + 1}. ${item}`;
                        queueDisplay.appendChild(div);
                    });
                });
            }
            
            function listAudioFiles() {
                fetch('/api/audio-files')
                .then(response => response.json())
                .then(data => {
                    const audioDisplay = document.getElementById('audioFilesDisplay');
                    audioDisplay.innerHTML = '';
                    
                    if (data.files.length === 0) {
                        audioDisplay.innerHTML = '<p>No audio files generated yet.</p>';
                        return;
                    }
                    
                    data.files.forEach((file, index) => {
                        const div = document.createElement('div');
                        div.className = 'queue-item';
                        div.innerHTML = `
                            <strong>${file.filename}</strong> (${file.size} bytes)
                            <br><small>Generated: ${file.timestamp}</small>
                            <br><small>📁 Saved in: audio_outputs/</small>
                        `;
                        audioDisplay.appendChild(div);
                    });
                });
            }
            
            function clearAudioFiles() {
                if (confirm('Are you sure you want to delete all audio files?')) {
                    fetch('/api/clear-audio', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('Audio files cleared');
                            listAudioFiles();
                        } else {
                            alert('Error: ' + data.error);
                        }
                    });
                }
            }
            
            function playAllAudio() {
                fetch('/api/play-audio', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Audio playback started!');
                        getPlaybackStatus();
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function stopAudio() {
                fetch('/api/stop-audio', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Audio playback stopped');
                        getPlaybackStatus();
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function getPlaybackStatus() {
                fetch('/api/playback-status')
                .then(response => response.json())
                .then(data => {
                    const statusDiv = document.getElementById('playbackStatus');
                    statusDiv.innerHTML = `
                        <p><strong>Status:</strong> ${data.is_playing ? 'Playing' : 'Stopped'}</p>
                        <p><strong>Current File:</strong> ${data.current_file || 'None'}</p>
                        <p><strong>Total Files:</strong> ${data.total_files}</p>
                        <p><strong>Audio Available:</strong> ${data.audio_available ? 'Yes' : 'No'}</p>
                    `;
                });
            }
            
            function generateAndPlay() {
                // Generate 3 random sentences
                const sentences = [
                    "The beautiful mountain shines gracefully in the starlit sky.",
                    "A mysterious forest drifts peacefully while touching the earth.",
                    "The ancient temple blooms freely through the crystal cave."
                ];
                
                let completed = 0;
                const total = sentences.length;
                
                alert(`🎲 Generating ${total} random sentences and will play them automatically!`);
                
                // Add each sentence to the queue
                sentences.forEach((sentence, index) => {
                    fetch('/api/add-text', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({text: sentence})
                    })
                    .then(response => response.json())
                    .then(data => {
                        completed++;
                        console.log(`Added sentence ${completed}/${total}: ${sentence}`);
                        
                        // When all sentences are added, wait a bit then start playback
                        if (completed === total) {
                            setTimeout(() => {
                                alert('🎵 All sentences generated! Starting playback...');
                                playAllAudio();
                            }, 2000);
                        }
                    })
                    .catch(error => {
                        console.error('Error adding sentence:', error);
                        completed++;
                    });
                });
            }
            
            // Load status on page load
            getStatus();
            listAudioFiles();
        </script>
    </body>
    </html>
    """)

@app.route("/api/status")
def get_status():
    """Get current status of TTS service and queue"""
    return jsonify({
        "tts_available": tts_service is not None,
        "queue_length": len(text_queue),
        "queue": text_queue.copy()
    })

@app.route("/api/add-text", methods=["POST"])
def add_text():
    """Add text to the TTS queue"""
    if not tts_service:
        return jsonify({"success": False, "error": "TTS service not available"})
    
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"success": False, "error": "No text provided"})
    
    text = data['text'].strip()
    if not text:
        return jsonify({"success": False, "error": "Empty text"})
    
    # Add to our queue
    text_queue.append(text)
    
    # Add to TTS service queue
    tts_service.enqueue(text)
    
    return jsonify({"success": True, "message": "Text added to queue"})

@app.route("/api/play-queue", methods=["POST"])
def play_queue():
    """Play all items in the queue"""
    if not tts_service:
        return jsonify({"success": False, "error": "TTS service not available"})
    
    if not text_queue:
        return jsonify({"success": False, "error": "Queue is empty"})
    
    # All items are already queued in TTS service, just wait for completion
    return jsonify({"success": True, "message": "Queue playback started"})

@app.route("/api/clear-queue", methods=["POST"])
def clear_queue():
    """Clear the text queue"""
    global text_queue
    text_queue.clear()
    return jsonify({"success": True, "message": "Queue cleared"})

@app.route("/api/queue-length")
def queue_length():
    """Get the current queue length"""
    return jsonify({"length": len(text_queue)})

@app.route("/api/tts-info")
def tts_info():
    """Get information about the TTS service"""
    if not tts_service:
        return jsonify({"available": False, "error": "TTS service not initialized"})
    
    return jsonify({
        "available": True,
        "default_voice": tts_service._default_voice,
        "default_model": tts_service._default_model
    })

@app.route("/api/audio-files")
def list_audio_files():
    """List all generated audio files"""
    audio_dir = "audio_outputs"
    if not os.path.exists(audio_dir):
        return jsonify({"files": []})
    
    files = []
    for filepath in glob.glob(os.path.join(audio_dir, "*.mp3")):
        filename = os.path.basename(filepath)
        stat = os.stat(filepath)
        files.append({
            "filename": filename,
            "size": stat.st_size,
            "timestamp": time.ctime(stat.st_mtime)
        })
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return jsonify({"files": files})


@app.route("/api/clear-audio", methods=["POST"])
def clear_audio():
    """Delete all audio files"""
    audio_dir = "audio_outputs"
    if not os.path.exists(audio_dir):
        return jsonify({"success": True, "message": "No audio files to clear"})
    
    try:
        deleted_count = 0
        for filepath in glob.glob(os.path.join(audio_dir, "*.mp3")):
            os.remove(filepath)
            deleted_count += 1
        
        return jsonify({"success": True, "message": f"Deleted {deleted_count} audio files"})
    except Exception as e:
        return jsonify({"error": f"Failed to clear audio files: {str(e)}"}), 500

@app.route("/api/play-audio", methods=["POST"])
def play_audio():
    """Start playing all audio files in chronological order"""
    try:
        if not audio_player.audio_available:
            return jsonify({"success": False, "error": "Audio player not available"})
        
        if audio_player.is_playing:
            return jsonify({"success": False, "error": "Audio is already playing"})
        
        # Start playback in background thread
        audio_player.play_all_files_async()
        
        return jsonify({"success": True, "message": "Audio playback started"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start playback: {str(e)}"}), 500

@app.route("/api/stop-audio", methods=["POST"])
def stop_audio():
    """Stop current audio playback"""
    try:
        if not audio_player.is_playing:
            return jsonify({"success": False, "error": "No audio is currently playing"})
        
        audio_player.stop_playback()
        return jsonify({"success": True, "message": "Audio playback stopped"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to stop playback: {str(e)}"}), 500

@app.route("/api/playback-status")
def playback_status():
    """Get current playback status"""
    try:
        status = audio_player.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": f"Failed to get status: {str(e)}"}), 500

if __name__ == "__main__":
    print("Starting Flask TTS Application...")
    print("Make sure to set ELEVENLABS_API_KEY environment variable")
    app.run(debug=True, host='0.0.0.0', port=5000)
