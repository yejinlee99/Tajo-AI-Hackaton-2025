import os, json, base64, asyncio, websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
import logging # Import the logging module

# Configure logging
logging.basicConfig(level=logging.INFO, # Set the minimum logging level to INFO
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Get a logger for this module

load_dotenv()
app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5050))
# EC2 공개 IP 또는 도메인 설정
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN")  # 예: "http://your-ec2-ip:5050" 또는 "https://your-domain.com"

VOICE = "alloy"
SYSTEM_MESSAGE = """
당신은 호출형 택시 서비스의 음성 안내 챗봇입니다.

대화 시작 시 반드시 다음과 같이 인사하세요:
"안녕하세요! 택시 호출 서비스입니다. 먼저 출발지를 알려주시겠어요?"

그 다음 목표는 사용자의 "출발지"와 "도착지" 정보를 자연스럽고 정확하게 파악하는 것입니다.

규칙:
- 사용자가 명확히 대답하지 않으면 다시 한번 친절하게 질문하세요.
- 지명, 건물 이름, 병원, 역, 아파트, 회사 등 어떤 표현도 이해하고 받아들이세요.
- 사용자가 "여기" 또는 "내 위치"라고 말하면 "정확한 위치를 알기 위해 주소나 근처 건물 이름을 알려달라"고 답하세요.
- 출발지와 도착지를 모두 확인하면 "이제 택시를 배차해드릴게요. 잠시만 기다려주세요."라고 마무리하세요.
- 한 번에 하나의 질문만 하세요.
- 톤은 공손하고 자연스러우며 부담스럽지 않게 유지하세요.
- 항상 한국어로 대답하세요.
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    logger.info("Root endpoint accessed.")
    return "<h1>gpt-4o-mini Realtime Test Server Running</h1>"


@app.get("/health")
async def health_check():
    logger.info("Health check endpoint accessed.")
    return {"status": "healthy", "domain": PUBLIC_DOMAIN}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    logger.info("=== INCOMING CALL DEBUG INFO ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")

    # POST 데이터 확인
    if request.method == "POST":
        try:
            form_data = await request.form()
            logger.info(f"Form data: {dict(form_data)}")
        except Exception as e:
            logger.error(f"Error reading form data: {e}")

    # Query parameters 확인
    logger.info(f"Query params: {dict(request.query_params)}")

    # PUBLIC_DOMAIN 확인
    logger.info(f"PUBLIC_DOMAIN env var: {PUBLIC_DOMAIN}")

    response = VoiceResponse()

    # PUBLIC_DOMAIN 사용 (환경변수에서 설정)
    if PUBLIC_DOMAIN:
        base_url = PUBLIC_DOMAIN
        logger.info(f"Using PUBLIC_DOMAIN: {base_url}")
    else:
        # fallback: request에서 추출
        scheme = "https" if request.url.scheme == "https" else "http"
        host = request.headers.get("host", request.url.netloc)
        base_url = f"{scheme}://{host}"
        logger.info(f"Using fallback URL: {base_url}")

    # WebSocket URL 생성
    websocket_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/media-stream"
    logger.info(f"Generated WebSocket URL: {websocket_url}")

    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)

    twiml_response = str(response)
    logger.info(f"Generated TwiML Response: {twiml_response}")
    logger.info(f"=== END DEBUG INFO ===")

    return HTMLResponse(content=twiml_response, media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    logger.info("=== WEBSOCKET CONNECTION ATTEMPT ===")
    logger.info(f"Client headers: {websocket.headers}")
    logger.info(f"Client query params: {websocket.query_params}")

    try:
        await websocket.accept()
        logger.info("WebSocket connection established successfully")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection: {e}")
        return

    logger.info("Attempting to connect to OpenAI WebSocket...")

    try:
        async with websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview',
                additional_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
        ) as openai_ws:
            logger.info("Successfully connected to OpenAI WebSocket")
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
                        logger.debug(f"Received from Twilio: {data['event']}")

                        # 수정된 부분: openai_ws가 특정 타입인지도 함께 확인합니다.
                        if data['event'] == 'media':
                            if openai_ws and not openai_ws.is_closed:
                                latest_media_timestamp = int(data['media']['timestamp'])
                                await openai_ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": data['media']['payload']
                                }))
                            else:
                                logger.warning(
                                    f"Received media but OpenAI WebSocket is not open or closed, websocket state : {openai_ws.closed if openai_ws else 'None'}"
                                )

                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            logger.info(f"Stream started with SID: {stream_sid}")

                        elif data['event'] == 'mark' and mark_queue:
                            mark_queue.pop(0)

                        elif data['event'] == 'stop':
                            logger.info("Stream stopped")
                            break

                except WebSocketDisconnect:
                    logger.info("Twilio WebSocket disconnected")

                    if openai_ws and not openai_ws.closed:
                        await openai_ws.close()

                except Exception as e:
                    logger.error(f"Error in receive_from_twilio: {e}", exc_info=True)

            async def send_to_twilio():
                nonlocal last_assistant_item, response_start_timestamp_twilio
                session_initialized = False
                initial_response_sent = False  # 첫 응답 전송 여부 추가

                try:
                    async for msg in openai_ws:
                        res = json.loads(msg)
                        logger.debug(f"Received from OpenAI: {res.get('type', 'unknown')}") # Use debug for high volume events

                        if res.get('type') == 'response.audio.delta' and 'delta' in res:
                            payload = base64.b64encode(base64.b64decode(res['delta'])).decode()
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload}
                            })

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp
                                logger.info("Started sending audio response to Twilio")

                            if res.get('item_id'):
                                last_assistant_item = res['item_id']
                            await send_mark(websocket, stream_sid)

                        elif res.get('type') == 'input_audio_buffer.speech_started' and last_assistant_item:
                            logger.info("Speech interruption detected")
                            await handle_interruption()

                        elif res.get('type') == 'error':
                            logger.error(f"OpenAI Error: {res}")

                        elif res.get('type') == 'session.created':
                            logger.info("OpenAI session created successfully")
                            session_initialized = True
                            # session.created 후에 첫 응답 생성 (send_session_update에서 이미 준비된 메시지)
                            if not initial_response_sent:
                                logger.info("Session ready - creating initial response")
                                await openai_ws.send(json.dumps({
                                    "type": "response.create"
                                }))
                                initial_response_sent = True

                        elif res.get('type') == 'response.created':
                            logger.info("OpenAI response created")

                        elif res.get('type') == 'response.done':
                            logger.info("OpenAI response completed")
                            # 응답 완료 후 상태 리셋
                            response_start_timestamp_twilio = None

                        elif res.get('type') == 'input_audio_buffer.speech_stopped':
                            if session_initialized and initial_response_sent:  # 초기 응답 후에만 적용
                                logger.info("User speech stopped - committing audio buffer")
                                await openai_ws.send(json.dumps({
                                    "type": "input_audio_buffer.commit"
                                }))
                            else:
                                logger.warning("Session not ready yet, skipping commit for speech_stopped")

                        elif res.get('type') == 'input_audio_buffer.committed':
                            logger.info("Audio buffer committed - creating response")
                            await openai_ws.send(json.dumps({
                                "type": "response.create"
                            }))

                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}", exc_info=True)

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
                logger.info("Handled speech interruption: truncated conversation item and cleared Twilio stream.")


            async def send_mark(ws, sid):
                if sid:
                    await ws.send_json({
                        "event": "mark",
                        "streamSid": sid,
                        "mark": {"name": "responsePart"}
                    })
                    mark_queue.append("responsePart")
                    logger.debug("Sent mark to Twilio.")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

    except Exception as e:
        logger.error(f"Error in media stream: {e}", exc_info=True)
    finally:
        logger.info("WebSocket connection closed")

async def send_session_update(openai_ws):
    # 세션 설정
    await openai_ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["audio", "text"],
            "temperature": 0.6
        }
    }))
    logger.info("Sent session.update to OpenAI.")


    # 시스템이 먼저 인사하도록 메시지 준비 (응답 생성은 session.created에서)
    await openai_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "assistant",
            "content": [{
                "type": "text",
                "text": "안녕하세요! 택시 호출 서비스입니다. 먼저 출발지를 알려주시겠어요?"
            }]
        }
    }))
    logger.info("Prepared initial assistant message for OpenAI.")


# Run server
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting uvicorn server on host 0.0.0.0 and port {PORT}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)