from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from agents import AGENTS, generate_agent_response
from stt import transcribe_audio
from tts import text_to_speech
import base64
import traceback
from typing import List, Dict
import json

app = FastAPI()

MODERATOR = {
    "name": "Moderator",
    "role": "Discussion Moderator",
    "personality": "Professional, neutral, and guiding the conversation",
    "background": "Experienced in facilitating group discussions and debates"
}

def get_moderator_intro(topic: str) -> str:
    return (
        f"Welcome to our group discussion. Today, we'll be exploring the topic: '{topic}'. "
        "I'll be moderating this discussion to ensure a productive exchange of ideas. "
        "Each participant will share their perspective, and we encourage everyone, including our audience, "
        "to contribute thoughtfully. Let's begin with our first speaker."
    )

def format_conversation_context(conversation: List[str], username: str = "User") -> str:
    formatted = []
    for entry in conversation:
        if entry.startswith("You:"):
            formatted.append(entry.replace("You:", f"{username}:"))
        else:
            formatted.append(entry)
    return "\n".join(formatted)

@app.websocket("/ws/gd")
async def gd_room(websocket: WebSocket):
    await websocket.accept()
    print("connection open")
    topic = "Is AI a threat to human jobs?"
    conversation = []
    username = "Mokksh"
    is_user_speaking = False
    silence_threshold = 0.5
    last_audio = None

    async def send_agent_message(agent: Dict, text: str) -> bool:
        try:
            print(f"Generating audio for {agent['name']}: {text}")
            audio_b64 = text_to_speech(text, lang='en')
            print(f"Generated audio size: {len(audio_b64)} bytes")
            await websocket.send_json({
                "sender": agent['name'],
                "audio": audio_b64
            })
            await asyncio.sleep(len(text) * 0.03 + 1)
            return True
        except WebSocketDisconnect:
            print("WebSocket disconnected during message send")
            return False
        except Exception as e:
            print(f"Error sending agent message: {str(e)}")
            traceback.print_exc()
            return False

    async def start_user_turn():
        nonlocal is_user_speaking
        is_user_speaking = True
        await websocket.send_json({
            "type": "control",
            "action": "start_recording"
        })

    async def end_user_turn():
        nonlocal is_user_speaking
        is_user_speaking = False
        await websocket.send_json({
            "type": "control",
            "action": "stop_recording"
        })

    try:
        mod_intro = get_moderator_intro(topic)
        conversation.append(f"{MODERATOR['name']}: {mod_intro}")
        if not await send_agent_message(MODERATOR, mod_intro):
            return

        for agent in AGENTS:
            context = format_conversation_context(conversation, username)
            text = generate_agent_response(agent, topic, context)
            conversation.append(f"{agent['name']}: {text}")
            if not await send_agent_message(agent, text):
                return

        await start_user_turn()

        while True:
            try:
                message = await websocket.receive()
                if message["type"] == "websocket.receive":
                    if "bytes" in message and message["bytes"]:
                        print("✅ Got raw audio bytes")
                        last_audio = message["bytes"]

                    if "text" in message:
                        try:
                            data = json.loads(message["text"])

                            if data.get("type") == "audio_chunk":
                                print("✅ Received audio_chunk from frontend")
                                last_audio = base64.b64decode(data["data"])

                            elif data.get("type") == "control" and data["action"] == "end_turn":
                                if is_user_speaking:
                                    await end_user_turn()
                                    if last_audio:
                                        final_text = transcribe_audio(last_audio)
                                        print(f"✅ Transcribed text: {final_text}")
                                        if final_text:
                                            conversation.append(f"{username}: {final_text}")
                                            for agent in AGENTS:
                                                context = format_conversation_context(conversation, username)
                                                text = generate_agent_response(agent, topic, context)
                                                conversation.append(f"{agent['name']}: {text}")
                                                if not await send_agent_message(agent, text):
                                                    return
                                            await start_user_turn()

                            elif data.get("type") == "silence_detected":
                                if is_user_speaking and data.get("duration", 0) >= silence_threshold:
                                    await end_user_turn()
                                    if last_audio:
                                        final_text = transcribe_audio(last_audio)
                                        print(f"✅ Transcribed text: {final_text}")
                                        if final_text:
                                            conversation.append(f"{username}: {final_text}")
                                            for agent in AGENTS:
                                                context = format_conversation_context(conversation, username)
                                                text = generate_agent_response(agent, topic, context)
                                                conversation.append(f"{agent['name']}: {text}")
                                                if not await send_agent_message(agent, text):
                                                    return
                                            await start_user_turn()

                        except json.JSONDecodeError:
                            print("⚠️ Could not parse text message")

            except WebSocketDisconnect:
                print("WebSocket disconnected")
                break
            except Exception as e:
                print(f"Error in websocket communication: {str(e)}")
                traceback.print_exc()
                break

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"Error in main websocket loop: {str(e)}")
        traceback.print_exc()
    finally:
        print("WebSocket connection closed")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
