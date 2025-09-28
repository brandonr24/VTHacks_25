import os
import queue
import threading
from typing import Iterable, Optional

from elevenlabs import play, save
from elevenlabs.client import ElevenLabs


class TTSService:
    """Queue-based text-to-speech helper around the ElevenLabs API."""

    def __init__(
        self,
        default_voice: str = "2EiwWnXFnvU5JabPnv8n",  # Clyde voice ID
        default_model: str = "eleven_monolingual_v1",
    ) -> None:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable is required")

        self._client = ElevenLabs(api_key=api_key)
        self._default_voice = default_voice
        self._default_model = default_model

        self._queue: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, text: str, voice: Optional[str] = None, model: Optional[str] = None) -> None:
        """Schedule *text* for immediate TTS playback."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        self._queue.put(
            (
                text,
                voice or self._default_voice,
                model or self._default_model,
            )
        )

    def enqueue_many(self, texts: Iterable[str], voice: Optional[str] = None, model: Optional[str] = None) -> None:
        """Convenience helper to queue several strings in order."""
        for text in texts:
            self.enqueue(text, voice=voice, model=model)

    def drain_external_queue(
        self,
        text_queue: "queue.Queue[str]",
        voice: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Pull every string from *text_queue* and enqueue it here."""
        while True:
            try:
                text = text_queue.get_nowait()
            except queue.Empty:
                break
            self.enqueue(text, voice=voice, model=model)
            text_queue.task_done()

    def text_to_speech(self, text: str, voice: Optional[str] = None, model: Optional[str] = None):
        """Generate raw audio for *text* using ElevenLabs."""
        try:
            voice_id = voice or self._default_voice
            model_id = model or self._default_model
            
            # Use the client's text_to_speech.convert method
            audio_generator = self._client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id=model_id
            )
            
            # Convert the generator to bytes
            audio_bytes = b"".join(audio_generator)
            return audio_bytes
            
        except Exception as exc:  # pragma: no cover - network failure
            print(f"Error generating speech: {exc}")
            return None

    @staticmethod
    def play_audio(audio) -> None:
        """Play audio immediately."""
        if audio:
            play(audio)

    @staticmethod
    def save_audio(audio, filename: str) -> None:
        """Persist *audio* to *filename*."""
        if audio:
            save(audio, filename)
            print(f"Audio saved to {filename}")

    def wait_until_empty(self) -> None:
        """Block until the internal queue has been processed."""
        self._queue.join()

    def shutdown(self) -> None:
        """Flush outstanding work and stop the background worker."""
        if not self._worker.is_alive():
            return
        self._stop_event.set()
        self._queue.put(("", self._default_voice, self._default_model))
        self._worker.join(timeout=5)

    # ------------------------------------------------------------------
    # Worker internals
    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        import time
        import os
        
        # Create output directory if it doesn't exist
        output_dir = "audio_outputs"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        while True:
            try:
                text, voice, model = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue

            if self._stop_event.is_set() and not text:
                self._queue.task_done()
                break

            audio = self.text_to_speech(text, voice=voice, model=model)
            if audio:
                # Generate filename with timestamp
                timestamp = int(time.time() * 1000)  # milliseconds
                filename = f"tts_output_{timestamp}.mp3"
                filepath = os.path.join(output_dir, filename)
                
                # Save audio to file
                self.save_audio(audio, filepath)
                print(f"Audio saved to: {filepath}")
                
                # Optionally play as well (comment out if you only want to save)
                # self.play_audio(audio)
            self._queue.task_done()

        # Drain leftover sentinel items so join() cannot deadlock
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()


