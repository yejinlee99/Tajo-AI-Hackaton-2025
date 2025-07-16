# app.py
import os, json, base64, asyncio, websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5050))
# EC2 공개 IP 또는 도메인 설정
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN")  # 예: "http://your-ec2-ip:5050" 또는 "https://your-domain.com"

VOICE = "alloy"
SYSTEM_MESSAGE = "You are a helpful, friendly AI assistant. Keep your responses brief and cheerful."


@app.get("/", response_class=HTMLResponse)
async def index():
    return "<h1>gpt-4o-mini Realtime Test Server Running</h1>"


@app.get("/health")
async def health_check():
    return {"status": "healthy", "domain": PUBLIC_DOMAIN}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    print(f"Incoming call - Headers: {request.headers}")
    print(f"Incoming call - URL: {request.url}")

    response = VoiceResponse()

    # PUBLIC_DOMAIN 사용 (환경변수에서 설정)
    if PUBLIC_DOMAIN:
        base_url = PUBLIC_DOMAIN
    else:
        # fallback: request에서 추출
        scheme = "https" if request.url.scheme == "https" else "http"
        host = request.headers.get("host", request.url.netloc)
        base_url = f"{scheme}://{host}"

    # WebSocket URL 생성
    websocket_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/media-stream"

    print(f"WebSocket URL: {websocket_url}")

    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)

    twiml_response = str(response)
    print(f"TwiML Response: {twiml_response}")

    return HTMLResponse(content=twiml_response, media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    print("WebSocket connection attempt")
    await websocket.accept()
    print("WebSocket connection established")

    try:
        async with websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
        ) as openai_ws:
            print("Connected to OpenAI WebSocket")
            await send_session_update(openai_ws)
            stream_sid = None
            mark_queue = []
            latest_media_timestamp = 0
            last_assistant_item = None
            response_start_timestamp_twilio = None

            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp
                try:
                    async for msg in websocket.iter_text():
                        data = json.loads(msg)
                        print(f"Received from Twilio: {data['event']}")

                        if data['event'] == 'media' and openai_ws.open:
                            latest_media_timestamp = int(data['media']['timestamp'])
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Stream started with SID: {stream_sid}")
                        elif data['event'] == 'mark' and mark_queue:
                            mark_queue.pop(0)
                        elif data['event'] == 'stop':
                            print("Stream stopped")
                            break
                except WebSocketDisconnect:
                    print("Twilio WebSocket disconnected")
                    if openai_ws.open:
                        await openai_ws.close()
                except Exception as e:
                    print(f"Error in receive_from_twilio: {e}")

            async def send_to_twilio():
                nonlocal last_assistant_item, response_start_timestamp_twilio
                try:
                    async for msg in openai_ws:
                        res = json.loads(msg)
                        if res.get('type') == 'response.audio.delta' and 'delta' in res:
                            payload = base64.b64encode(base64.b64decode(res['delta'])).decode()
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload}
                            })

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp

                            if res.get('item_id'):
                                last_assistant_item = res['item_id']
                            await send_mark(websocket, stream_sid)

                        elif res.get('type') == 'input_audio_buffer.speech_started' and last_assistant_item:
                            await handle_interruption()
                except Exception as e:
                    print(f"Error in send_to_twilio: {e}")

            async def handle_interruption():
                nonlocal last_assistant_item, response_start_timestamp_twilio
                elapsed = latest_media_timestamp - response_start_timestamp_twilio
                await openai_ws.send(json.dumps({
                    "type": "conversation.item.truncate",
                    "item_id": last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed
                }))
                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })
                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

            async def send_mark(ws, sid):
                if sid:
                    await ws.send_json({
                        "event": "mark",
                        "streamSid": sid,
                        "mark": {"name": "responsePart"}
                    })
                    mark_queue.append("responsePart")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

    except Exception as e:
        print(f"Error in media stream: {e}")
    finally:
        print("WebSocket connection closed")


async def send_session_update(openai_ws):
    await openai_ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.6
        }
    }))

    await openai_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": "Hello! You're now connected to a gpt-4o-mini voice assistant. Feel free to ask anything."
            }]
        }
    }))
    await openai_ws.send(json.dumps({"type": "response.create"}))


# Run server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=PORT)