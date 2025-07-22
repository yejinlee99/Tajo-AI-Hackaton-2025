import os, json, base64, asyncio, websockets, logging
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from websockets.protocol import State

# 로깅 설정 - INFO 레벨로 변경
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# 환경변수 로드
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

# 도메인 활성화 확인용
@app.get("/", response_class=HTMLResponse)
async def index():
    return "<h1>gpt-4o-mini Realtime Test Server Running</h1>"

# 헬스체크
@app.get("/health")
async def health_check():
    return {"status": "healthy", "domain": PUBLIC_DOMAIN}

# incoming-call 엔드포인트로 GET/POST요청 허용
@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    # 전화 수신시 로깅
    logger.info("Incoming call received")

    response = VoiceResponse()

    # PUBLIC_DOMAIN 사용 (환경변수에서 설정)
    if PUBLIC_DOMAIN:
        base_url = PUBLIC_DOMAIN
    # else문 없어도 되는지 확인 필요할 듯
    else:
        # fallback: request에서 추출
        scheme = "https" if request.url.scheme == "https" else "http"
        host = request.headers.get("host", request.url.netloc)
        base_url = f"{scheme}://{host}"

    # WebSocket URL 생성
    # https와 wss가 보안이 강화된 프로토콜
    websocket_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/media-stream"
    logger.info(f"WebSocket URL: {websocket_url}")

    # Twiml 명령어 생성 및 반환
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")

# Twiml 명령어를 통해 websocket의 media-stream 엔드포인트에 연결 요청
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    # websocket 연결 시도 로깅
    logger.info("WebSocket connection attempt")

    try:
        await websocket.accept()
        # 웹소켓 연결 성공 로깅
        logger.info("WebSocket connection established")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection: {e}")
        return

    logger.info("Connecting to OpenAI WebSocket...")
    # 연결 시도/성공/실패 로깅과 비동기적으로 openai websocket과의 연결이 일어남
    try:
        async with websockets.connect(
                # gpt-4o-mini-realtime-preview 모델 사용
                'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview',
                additional_headers={
                    # api key 입력
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    # 모델이 beta버전인 경우 추가해야 하는 헤더
                    "OpenAI-Beta": "realtime=v1"
                }
        ) as openai_ws: # openai websocket sesssion 객체
            # openai websocket 연결 로깅
            logger.info("Connected to OpenAI WebSocket")
            # session객체의 상태가 update되면서 통화중 기능이 전환됨
            await send_session_update(openai_ws)
            # 연결 전 변수 초기화
            stream_sid = None
            mark_queue = []
            latest_media_timestamp = 0
            last_assistant_item = None
            response_start_timestamp_twilio = None

            # twilio로부터 메시지를 수신하는 함수
            async def receive_from_twilio():
                # 이하 (거의) 모든 함수는 다른 함수의 변수를 호출하고 수정하기 위해 nonlocal 설정
                nonlocal stream_sid, latest_media_timestamp
                try:
                    # twilio가 보내는 텍스트 메시지를 수신하고 json(dict)로 파싱
                    async for msg in websocket.iter_text():
                        data = json.loads(msg)
                        # event == media -> 사용자가 음성을 입력 and 세션 상태가 열려있는 경우
                        if data['event'] == 'media' and openai_ws.state == State.OPEN:
                            # timestamp 기록
                            #    이 타임스탬프는 밀리초 단위이며, 통화 시작 시점부터의 경과 시간을 나타냅니다.
                            #    이를 int()로 정수형으로 변환하여 latest_media_timestamp 변수에 저장합니다.
                            #    이 변수는 주로 'handle_interruption' 함수에서 사용자 말 끊기를 감지했을 때,
                            #    AI가 발화 중인 오디오를 어디까지 잘라야 할지 계산하는 데 사용됩니다.
                            latest_media_timestamp = int(data['media']['timestamp'])
                            # openai api로 json형식의 메시지 전송
                            await openai_ws.send(json.dumps({
                                # OpenAI Realtime API에 실시간으로 들어오는 오디오 데이터를 내 모델의 입력 오디오 버퍼에 계속 추가
                                # OpenAI는 이 버퍼에 쌓인 오디오를 사용하여 음성-텍스트 변환(STT)을 수행하고 사용자 발화를 감지
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))
                        # event == start -> stream 시작
                        elif data['event'] == 'start':
                            # 스트림 id 저장
                            stream_sid = data['start']['streamSid']
                            # 스트림 id 로깅
                            logger.info(f"Stream started: {stream_sid}")
                        # interrupt(사용자가 AI의 말을 끊고 말하는 경우) AI의 발화를 중단하기 위한 이벤트
                        elif data['event'] == 'mark' and mark_queue:
                            mark_queue.pop(0)
                        # event == stop -> 스트림(통화 연결) 종료
                        elif data['event'] == 'stop':
                            # stream stop 로깅
                            logger.info("Stream stopped")
                            break
                # 연결이 끊어지는 경우 예외처리
                except WebSocketDisconnect:
                    logger.warning("Twilio disconnected")
                    if openai_ws.state == State.OPEN:
                        await openai_ws.close()
                except Exception as e:
                    logger.error(f"Error in receive_from_twilio: {e}")

            # openai websocket에서 twilio로 데이터를 보내는 함수
            async def send_to_twilio():
                nonlocal last_assistant_item, response_start_timestamp_twilio
                try:
                    # openai websocket session 객체로부터 메시지 수신
                    async for msg in openai_ws:
                        res = json.loads(msg)
                        event_type = res.get('type', 'unknown')
                        # openai가 보내준 base64를 디코딩하고, 다시 twilio가 요구하는 형식의 base64로 인코딩
                        if res.get('type') == 'response.audio.delta' and 'delta' in res:
                            payload = base64.b64encode(base64.b64decode(res['delta'])).decode()
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload}
                            })
                            # timestamp가 없다 == 이번 AI 응답의 시작점
                            if response_start_timestamp_twilio is None:
                                # 응답 시작 timestamp 찍고 로깅
                                response_start_timestamp_twilio = latest_media_timestamp
                                logger.info("AI response started")

                            # interrupt 처리
                            if res.get('item_id'):
                                last_assistant_item = res['item_id']
                            await send_mark(websocket, stream_sid)

                        # 사용자 음성 입력 중단시 로깅
                        elif res.get('type') == 'input_audio_buffer.speech_stopped':
                            logger.info("User speech stopped")

                        # 사용자 입력 text화 완료시 로깅
                        elif res.get('type') == 'conversation.item.input_audio_transcription.completed':
                            transcript = res.get('transcript', '')
                            logger.info(f"User: {transcript}")

                        # AI 응답 text화 완료시 로깅
                        elif res.get('type') == 'response.audio_transcript.done':
                            transcript = res.get('transcript', '')
                            logger.info(f"AI: {transcript}")

                        # AI 응답 완료시 로깅 + 타임스탬프 초기화
                        elif res.get('type') == 'response.done':
                            logger.info("AI response completed")
                            response_start_timestamp_twilio = None

                        # 사용자 발화 시작 and AI 응답이 있는 상황 -> interrupt 로깅 + interrupt 처리함수 호출
                        elif res.get('type') == 'input_audio_buffer.speech_started' and last_assistant_item:
                            logger.info("Speech interruption detected")
                            await handle_interruption()

                        # openai api가 보내준 오류메시지 로깅
                        elif res.get('type') == 'error':
                            logger.error(f"OpenAI Error: {res}")

                # 그 외 오류 로깅
                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}")
                    import traceback
                    traceback.print_exc()

            # interrupt 처리 함수
            async def handle_interruption():
                nonlocal last_assistant_item, response_start_timestamp_twilio

                # timestamp가 None -> AI 응답이 생성/처리되고 있지만 아직 시작되지 않음
                if response_start_timestamp_twilio is None:
                    logger.warning("Interruption detected but AI response hasn't started yet")
                    return
                # 오디오 잘라낼 시간 계산
                elapsed = latest_media_timestamp - response_start_timestamp_twilio
                # 다시 openai에게 interrupt 처리를 위한 메시지 전송
                await openai_ws.send(json.dumps({
                    # 말 그만해.
                    "type": "conversation.item.truncate",
                    # 그만하라고 시킬 말의 id
                    "item_id": last_assistant_item,
                    "content_index": 0,
                    # 위에서 계산한 시간대로 말 자르기
                    "audio_end_ms": elapsed
                }))
                # twilio한테도 말 그만하라고 전달
                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })
                # 기타 변수 초기화
                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None
            # mark는 twilio가 서버로부터 받은 오디오 스트림을 재생하기 시작했을 때, 그 사실을 서버에 다시 알려주는 재생 동기화 및 확인 메커니즘
            async def send_mark(ws, sid):
                if sid:
                    await ws.send_json({
                        "event": "mark",
                        "streamSid": sid,
                        "mark": {"name": "responsePart"}
                    })
                    mark_queue.append("responsePart")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())
    # handle_media_stream 함수의 예외처리
    except Exception as e:
        logger.error(f"Error in media stream: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("WebSocket closed")

# openai websocket session 설정 전송
async def send_session_update(openai_ws):
    logger.info("Configuring OpenAI session")

    # 세션 설정
    await openai_ws.send(json.dumps({
        "type": "session.update",
        "session": {
            # 발화 턴 감지
            "turn_detection": {"type": "server_vad"},
            # 입/출력 오디오 포맷 설정
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            # 음성 모델 지정
            "voice": VOICE,
            # 프롬프트 시스템메시지
            "instructions": SYSTEM_MESSAGE,
            # 응답에 사용할 모달리티
            "modalities": ["audio", "text"],
            # 응답하는 AI의 창의성 조절(0~2, 높을수록 창의적)
            "temperature": 0.6
        }
    }))

    # 시스템이 먼저 인사하도록 설정. 제대로 작동하지 않고 있어서 디버깅 필요
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

    # AI가 응답을 생성하도록 트리거
    await openai_ws.send(json.dumps({
        "type": "response.create",
        "response": {
            "modalities": ["text", "audio"]
        }
    }))


# Run server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT)