# Flask TTS Application with ElevenLabs

A Flask web application that provides a Text-to-Speech (TTS) service using ElevenLabs API with a queue-based system for managing multiple text inputs.

## Features

- **Queue-based TTS**: Add multiple text inputs to a queue for sequential processing
- **Audio File Output**: Saves generated audio as MP3 files instead of just playing
- **Web Interface**: Simple HTML interface for testing and managing the TTS queue
- **REST API**: Full REST API for programmatic access
- **File Management**: Download individual files or all files as a zip archive
- **Real-time Status**: Monitor queue status and TTS service availability
- **Error Handling**: Robust error handling and service status monitoring

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get ElevenLabs API Key

1. Sign up at [ElevenLabs](https://elevenlabs.io/)
2. Get your API key from the dashboard
3. Create a `.env` file in the Backend directory:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your API key
ELEVENLABS_API_KEY=your_actual_api_key_here
```

### 3. Run the Application

```bash
cd Backend
python app.py
```

The application will start on `http://localhost:5000`

## Usage

### Web Interface

Visit `http://localhost:5000` to access the web interface where you can:

- Add text to the TTS queue
- Add multiple sentences at once
- View current queue status
- Play the entire queue
- Clear the queue

### API Endpoints

#### GET `/api/status`
Get current status of TTS service and queue
```json
{
  "tts_available": true,
  "queue_length": 3,
  "queue": ["Text 1", "Text 2", "Text 3"]
}
```

#### POST `/api/add-text`
Add text to the TTS queue
```json
{
  "text": "Hello, this is a test message."
}
```

#### POST `/api/play-queue`
Start playing all items in the queue

#### POST `/api/clear-queue`
Clear the text queue

#### GET `/api/queue-length`
Get current queue length
```json
{
  "length": 3
}
```

#### GET `/api/tts-info`
Get TTS service information
```json
{
  "available": true,
  "default_voice": "2EiwWnXFnvU5JabPnv8n",
  "default_model": "eleven_monolingual_v1"
}
```

#### GET `/api/audio-files`
List all generated audio files
```json
{
  "files": [
    {
      "filename": "tts_output_1703123456789.mp3",
      "size": 245760,
      "timestamp": "Mon Dec 20 10:30:45 2023"
    }
  ]
}
```

#### POST `/api/clear-audio`
Delete all audio files

## Testing

Visit the web interface at http://localhost:5000 to test all functionality:

- Add text to the TTS queue
- Generate random sentences
- Play audio files automatically
- Monitor queue and playback status

## Architecture

### Components

1. **TTSService** (`components/tts.py`): Core TTS functionality with queue management
2. **Flask App** (`app.py`): Web server with REST API and web interface
3. **Queue System**: Manages text inputs and processes them sequentially

### How it Works

1. Text is added to the Flask application's queue via API or web interface
2. The text is immediately queued in the TTS service for processing
3. The TTS service processes items sequentially using a background worker thread
4. Audio is generated using ElevenLabs API and saved as MP3 files in the `audio_outputs` directory
5. Files are automatically named with timestamps (e.g., `tts_output_1703123456789.mp3`)
6. The queue status is tracked and can be monitored via API
7. Generated audio files can be downloaded individually or as a zip archive

## Configuration

### Voice Settings

The default voice is set to "Clyde" (ID: `2EiwWnXFnvU5JabPnv8n`). You can modify this in the `TTSService` initialization in `app.py`.

### Model Settings

The default model is `eleven_monolingual_v1`. You can change this in the `TTSService` initialization.

## Error Handling

- **Missing API Key**: Application will start but TTS service will be unavailable
- **Network Issues**: TTS requests will fail gracefully with error messages
- **Empty Queue**: Play requests will return appropriate error messages
- **Invalid Text**: Empty or invalid text inputs are rejected

## Development

### Adding New Features

1. **New API Endpoints**: Add new routes in `app.py`
2. **TTS Customization**: Modify `TTSService` class in `components/tts.py`
3. **UI Improvements**: Update the HTML template in the `home()` function

### Debugging

- Check the console output for TTS service initialization status
- Use the `/api/status` endpoint to monitor queue state
- Check ElevenLabs API key is correctly set in environment variables

## Troubleshooting

### Common Issues

1. **"TTS service not available"**: Check your ElevenLabs API key
2. **No audio playback**: Ensure your system has audio output enabled
3. **Queue not processing**: Check if TTS service is properly initialized
4. **Network errors**: Verify internet connection and ElevenLabs API status

### Logs

The application provides console output for:
- TTS service initialization status
- Queue operations
- Error messages
- Service availability

## License

This project is part of the VTHacks 2025 development.
