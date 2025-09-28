#!/usr/bin/env python3
"""
Audio Player Component for TTS System.
Automatically plays audio files in chronological order based on creation time.
"""

import os
import time
import threading
import glob
from typing import List, Optional, Callable
import pygame
from datetime import datetime

class AudioPlayer:
    """Audio player that plays files in chronological order"""
    
    def __init__(self, audio_dir: str = "audio_outputs"):
        self.audio_dir = audio_dir
        self.is_playing = False
        self.current_file = None
        self.playback_thread = None
        self.stop_event = threading.Event()
        self.on_playback_start: Optional[Callable] = None
        self.on_playback_end: Optional[Callable] = None
        self.on_file_start: Optional[Callable] = None
        self.on_file_end: Optional[Callable] = None
        
        # Initialize pygame mixer
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            print("✅ Audio player initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize audio player: {e}")
            self.audio_available = False
            return
        
        self.audio_available = True
    
    def get_audio_files_sorted(self) -> List[dict]:
        """Get all audio files sorted by creation time (oldest first)"""
        if not os.path.exists(self.audio_dir):
            return []
        
        files = []
        for filepath in glob.glob(os.path.join(self.audio_dir, "*.mp3")):
            stat = os.stat(filepath)
            files.append({
                "path": filepath,
                "filename": os.path.basename(filepath),
                "created_time": stat.st_ctime,
                "size": stat.st_size,
                "created_datetime": datetime.fromtimestamp(stat.st_ctime)
            })
        
        # Sort by creation time (oldest first)
        files.sort(key=lambda x: x["created_time"])
        return files
    
    def play_file(self, filepath: str) -> bool:
        """Play a single audio file"""
        if not self.audio_available:
            print("❌ Audio not available")
            return False
        
        try:
            # Notify that file playback is starting
            if self.on_file_start:
                self.on_file_start(filepath)
            
            # Load and play the file
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            
            # Wait for playback to complete
            while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                time.sleep(0.1)
            
            # Notify that file playback ended
            if self.on_file_end:
                self.on_file_end(filepath)
            
            return True
            
        except Exception as e:
            print(f"❌ Error playing {filepath}: {e}")
            return False
    
    def play_all_files(self) -> None:
        """Play all audio files in chronological order"""
        if not self.audio_available:
            print("❌ Audio not available")
            return
        
        files = self.get_audio_files_sorted()
        if not files:
            print("📁 No audio files found")
            if self.on_playback_end:
                self.on_playback_end()
            return
        
        print(f"🎵 Found {len(files)} audio files to play")
        
        # Notify that playback is starting
        if self.on_playback_start:
            self.on_playback_start(files)
        
        self.is_playing = True
        self.stop_event.clear()
        
        try:
            for i, file_info in enumerate(files, 1):
                if self.stop_event.is_set():
                    break
                
                filepath = file_info["path"]
                filename = file_info["filename"]
                created_time = file_info["created_datetime"].strftime("%H:%M:%S")
                
                print(f"🎵 Playing {i}/{len(files)}: {filename} (created: {created_time})")
                self.current_file = filepath
                
                success = self.play_file(filepath)
                if not success:
                    print(f"❌ Failed to play {filename}")
                
                # Small delay between files
                if i < len(files) and not self.stop_event.is_set():
                    time.sleep(0.5)
        
        except KeyboardInterrupt:
            print("\n🛑 Playback interrupted by user")
        except Exception as e:
            print(f"❌ Playback error: {e}")
        finally:
            self.is_playing = False
            self.current_file = None
            
            # Notify that playback ended
            if self.on_playback_end:
                self.on_playback_end()
    
    def play_all_files_async(self) -> None:
        """Start playing all files in a separate thread"""
        if self.is_playing:
            print("🎵 Already playing audio")
            return
        
        self.playback_thread = threading.Thread(target=self.play_all_files, daemon=True)
        self.playback_thread.start()
    
    def stop_playback(self) -> None:
        """Stop current playback"""
        if not self.is_playing:
            print("❌ No playback in progress")
            return
        
        print("🛑 Stopping playback...")
        self.stop_event.set()
        
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        
        self.is_playing = False
        self.current_file = None
    
    def get_status(self) -> dict:
        """Get current playback status"""
        files = self.get_audio_files_sorted()
        return {
            "is_playing": self.is_playing,
            "current_file": self.current_file,
            "total_files": len(files),
            "audio_available": self.audio_available,
            "files": files
        }
    
    def cleanup(self) -> None:
        """Clean up resources"""
        self.stop_playback()
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2)
        pygame.mixer.quit()

# Global audio player instance
audio_player = AudioPlayer()

def get_audio_player() -> AudioPlayer:
    """Get the global audio player instance"""
    return audio_player

# Callback functions for Flask integration
def on_playback_start(files):
    """Called when playback starts"""
    print(f"🎵 Starting playback of {len(files)} files")

def on_playback_end():
    """Called when playback ends"""
    print("🎵 Playback completed")

def on_file_start(filepath):
    """Called when a file starts playing"""
    filename = os.path.basename(filepath)
    print(f"▶️  Now playing: {filename}")

def on_file_end(filepath):
    """Called when a file finishes playing"""
    filename = os.path.basename(filepath)
    print(f"✅ Finished: {filename}")

# Set up callbacks
audio_player.on_playback_start = on_playback_start
audio_player.on_playback_end = on_playback_end
audio_player.on_file_start = on_file_start
audio_player.on_file_end = on_file_end

