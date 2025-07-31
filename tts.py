from gtts import gTTS
from io import BytesIO
import base64


def text_to_speech(text, lang='en'):
    if not text:
        print("Warning: Empty text provided to text_to_speech")
        return ""

    try:
        tts = gTTS(text=text, lang=lang)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_data = base64.b64encode(buf.read()).decode('utf-8')
        print(f"Generated audio for text: '{text[:50]}...' (length: {len(audio_data)} bytes)")
        return audio_data
    except Exception as e:
        print(f"Error in text_to_speech: {str(e)}")
        return ""