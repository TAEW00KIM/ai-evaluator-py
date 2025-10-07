# main.py
import asyncio
import zipfile
import os
import shutil
import logging
import aiohttp
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

# --- 설정 ---
# 로깅 기본 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
)
logger = logging.getLogger(__name__)

# 애플리케이션 설정 모델 (환경변수 등으로 관리 가능)
class AppSettings(BaseModel):
    spring_callback_url: str = "http://localhost:8080/api/internal/submissions/{submissionId}/complete"
    spring_status_update_url: str = "http://localhost:8080/api/internal/submissions/{submissionId}/running" # ◀️ 상태 업데이트 URL 추가
    upload_base_dir: str = "/path/to/your/spring/uploads" # ◀️ Spring Boot의 'uploads' 폴더 절대 경로

settings = AppSettings()
app = FastAPI()

# --- DTO 모델 ---
class EvaluationRequest(BaseModel):
    submissionId: int
    filePath: str # Spring 서버가 전달하는 파일의 전체 경로

class EvaluationResult(BaseModel):
    score: float = Field(default=0.0)
    log: str

# --- 비동기 통신 헬퍼 ---
async def send_callback(session: aiohttp.ClientSession, url: str, data: dict):
    """Spring 서버로 HTTP POST 요청을 비동기로 보냅니다."""
    try:
        async with session.post(url, json=data) as response:
            if 200 <= response.status < 300:
                logger.info(f"Callback to {url} successful.")
            else:
                logger.error(f"Callback to {url} failed with status: {response.status}")
    except Exception as e:
        logger.error(f"Error during callback to {url}: {str(e)}")

# --- 핵심 채점 로직 ---
async def grade_submission(submission_id: int, zip_file_path: str):
    """실제 채점을 수행하는 함수"""
    grading_dir = f"grading_temp/{submission_id}"
    score = 0.0
    log_output = ""

    try:
        # 1. 채점용 임시 폴더 생성 (기존 폴더가 있다면 삭제)
        if os.path.exists(grading_dir):
            shutil.rmtree(grading_dir)
        os.makedirs(grading_dir)

        # 2. 제출된 zip 파일 압축 해제
        logger.info(f"[{submission_id}] 압축 해제 시작: {zip_file_path}")
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(grading_dir)
        logger.info(f"[{submission_id}] 압축 해제 완료.")
        
        # 3. 🚀 채점 스크립트 실행 (가장 중요한 부분)
        #    - 예: `python grade.py /path/to/grading_dir/`
        #    - Docker를 사용한다면 여기에 Docker 실행 명령어가 들어갑니다.
        #    - 보안을 위해 `timeout`을 설정하는 것이 매우 중요합니다.
        command = f"python grading_script.py {grading_dir}" # 예시 명령어
        
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # 10분 이상 실행되면 강제 종료 (Timeout)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

        if proc.returncode == 0:
            # 성공: stdout에서 점수와 로그를 파싱 (JSON 형태를 권장)
            # 예시: "{"score": 95.5, "log": "All tests passed."}"
            result = stdout.decode().strip()
            # result_data = json.loads(result)
            # score = result_data['score']
            # log_output = result_data['log']
            score = 100.0 # 임시 점수
            log_output = f"채점 성공!\n{result}"
            logger.info(f"[{submission_id}] 채점 스크립트 성공.")
        else:
            # 실패: stderr를 로그로 사용
            log_output = f"채점 스크립트 실행 오류:\n{stderr.decode()}"
            logger.error(f"[{submission_id}] 채점 스크립트 실패: {log_output}")

    except asyncio.TimeoutError:
        log_output = "채점 시간 초과 (10분). 무한 루프 또는 비효율적인 코드가 있는지 확인하세요."
        logger.error(f"[{submission_id}] 채점 시간 초과.")
    except Exception as e:
        log_output = f"채점 시스템 내부 오류 발생: {str(e)}"
        logger.error(f"[{submission_id}] 채점 시스템 오류: {log_output}")
    finally:
        # 4. 임시 폴더 삭제
        if os.path.exists(grading_dir):
            shutil.rmtree(grading_dir)
    
    return EvaluationResult(score=score, log=log_output)


async def run_evaluation_task(submission_id: int, file_path: str):
    """백그라운드에서 실행될 전체 채점 작업"""
    logger.info(f"[{submission_id}] 평가 시작. 파일 경로: {file_path}")
    
    async with aiohttp.ClientSession() as session:
        # 1. Spring 서버에 '채점 중' 상태 전송
        running_url = settings.spring_status_update_url.format(submissionId=submission_id)
        await send_callback(session, running_url, {})

        # 2. 실제 채점 로직 실행
        result_data = await grade_submission(submission_id, file_path)
        
        # 3. Spring 서버에 최종 결과 전송
        complete_url = settings.spring_callback_url.format(submissionId=submission_id)
        await send_callback(session, complete_url, result_data.dict())

# --- API 엔드포인트 ---
@app.post("/evaluate")
async def evaluate_submission_endpoint(request: EvaluationRequest, background_tasks: BackgroundTasks):
    submission_id = request.submissionId
    #  보안: Spring에서 받은 경로에서 파일 이름만 추출
    file_name = os.path.basename(request.filePath)
    # 안전한 경로 조합
    secure_file_path = os.path.join(settings.upload_base_dir, file_name)
    
    logger.info(f"[{submission_id}] 채점 요청 수신. 파일명: {file_name}")

    # 파일이 실제로 존재하는지 확인
    if not os.path.exists(secure_file_path):
        logger.error(f"[{submission_id}] 파일을 찾을 수 없음: {secure_file_path}")
        raise HTTPException(status_code=404, detail="File not found on grading server.")

    # 백그라운드에서 채점 작업 시작
    background_tasks.add_task(run_evaluation_task, submission_id, secure_file_path)
    
    return {"message": "Evaluation task accepted.", "submissionId": submission_id}

# 서버 실행 (uvicorn main:app --reload)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)