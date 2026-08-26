import os
import tempfile
import httpx
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment
from app.config import N8N_WEBHOOK_URL



def convert_to_wav(input_audio_path: str) -> str:
    """Converts web audio (webm/ogg/mp4) to standard PCM WAV for STT."""
    audio = AudioSegment.from_file(input_audio_path)
    temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    audio.export(temp_wav.name, format="wav")
    return temp_wav.name


def generate_tts_audio(text: str) -> str:
    """Generates MP3 audio from text using gTTS."""
    clean_text = text.replace("*", "").replace("_", "").replace("#", "").replace("`", "").strip()
    tts = gTTS(text=clean_text or "Done", lang="en", tld="co.in")
    temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(temp_mp3.name)
    return temp_mp3.name


def process_voice_command(audio_file_path: str, user_id: str, is_admin: bool = False) -> tuple[str, str, str]:
    """
    Connected Voice Pipeline:
    1. STT: Converts microphone audio to text transcript.
    2. n8n AI Agent: Sends text to your n8n workflow for intent resolution & booking tools.
    3. TTS: Converts n8n reply into spoken audio.
    """
    # 1. Speech Recognition (STT)
    recognizer = sr.Recognizer()
    wav_path = convert_to_wav(audio_file_path)

    user_text = ""
    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            user_text = recognizer.recognize_google(audio_data, language="en-IN")
    except Exception:
        user_text = ""
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

    if not user_text:
        reply = "Sorry, I could not hear that. Please speak again."
        return "", reply, generate_tts_audio(reply)

    # 2. Forward transcript to your n8n AI Agent Workflow
    reply = ""
    if N8N_WEBHOOK_URL:
        n8n_payload = {
            "message": user_text,
            "user_id": user_id,
            "session_id": f"voice_{user_id}",
            "channel": "voice",
            "is_admin": is_admin
        }
        try:
            with httpx.Client(timeout=35.0) as client:
                res = client.post(N8N_WEBHOOK_URL, json=n8n_payload)
                if res.status_code == 200:
                    data = res.json()
                    # Extract reply from n8n response payload
                    reply = data.get("reply") or data.get("output") or data.get("text") or str(data)
                else:
                    reply = "I encountered an issue connecting to the assistant workflow."
        except Exception as e:
            reply = f"Could not reach AI agent: {str(e)}"
    else:
        reply = "N8N_WEBHOOK_URL is not configured in backend environment."

    # 3. Convert n8n AI Reply to Voice Speech (TTS)
    output_audio_path = generate_tts_audio(reply)
    return user_text, reply, output_audio_path