import whisper
import tempfile
import os
import subprocess
import time

# Load the model once when the module is initialized
MODEL = whisper.load_model("base")

def transcribe_audio(audio_bytes):
    if audio_bytes is None:
        print("⚠️ Warning: No audio input received for transcription.")
        return "No audio input detected."

    input_temp = None
    output_temp = None
    try:
        # Save incoming audio to temporary file
        input_temp = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        input_temp.write(audio_bytes)
        input_temp.close()

        # Create temporary file for output
        output_temp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        output_temp.close()

        # Convert to WAV using FFmpeg
        conversion_command = [
            'ffmpeg',
            '-i', input_temp.name,
            '-acodec', 'pcm_s16le',
            '-ac', '1',
            '-ar', '16000',
            '-y',
            output_temp.name
        ]

        process = subprocess.Popen(conversion_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = process.communicate()

        if process.returncode != 0:
            print(f"FFmpeg conversion error:\n{stderr.decode()}")
            return "Error converting audio format"

        result = MODEL.transcribe(output_temp.name)

        if not result["text"].strip():
            print("⚠️ Whisper returned empty transcription")
            return "No speech detected."

        return result["text"]

    except Exception as e:
        print(f"Transcription error: {str(e)}")
        return "Sorry, I couldn't understand the audio."

    finally:
        time.sleep(0.2)  # Give Windows time to release handles
        for temp_file in [input_temp, output_temp]:
            if temp_file is not None:
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    print(f"⚠️ Could not delete temporary file: {e}")
