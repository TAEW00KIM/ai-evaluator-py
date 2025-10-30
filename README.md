# AI AutoGrader - Python Grading Server (ai-evaluator-py)

딥러닝 기초 과제 자동 채점 시스템의 **비동기 채점 워커 서버**입니다.

FastAPI로 구축되었으며, Spring Boot 백엔드 서버로부터 채점 요청을 받아 학생의 코드를 격리된 환경에서 실행하고, 그 결과를 다시 백엔드 서버로 콜백(callback) 전송하는 역할을 담당합니다.

---

## 🚀 프로젝트 아키텍처

이 시스템은 세 개의 독립된 서버로 구성되어 유기적으로 동작합니다.

1.  **Frontend (React)**: 사용자가 보는 웹 화면입니다. 백엔드 서버와만 통신합니다.
2.  **Backend (Spring Boot)**: 중앙 API 서버입니다. 프론트엔드에서 파일을 받아 저장 후, 이 Python 서버의 `/evaluate` API를 호출합니다.
3.  **Python Server (FastAPI)**: **(현재 리포지토리)** 실제 채점을 담당하는 격리된 워커입니다.
    * 백엔드와만 통신하며, 프론트엔드와는 직접 통신하지 않습니다.
    * 백엔드로부터 `POST /evaluate` 요청을 받으면(submissionId, filePath 포함), 즉시 200 OK를 반환하고 채점 작업을 **백그라운드 태스크**로 넘깁니다.
    * (백그라운드) `config.py`에 설정된 백엔드 URL로 `RUNNING` 상태 콜백을 보냅니다.
    * (백그라운드) `grading_temp/`에 임시 폴더를 만들고 학생의 zip 파일 압축을 풉니다.
    * (백그라운드) `grading_script.py`를 `subprocess`로 실행하여 채점합니다. (10분 타임아웃 적용)
    * (백그라운드) 스크립트의 `stdout` (JSON 형식)을 파싱하여 점수와 로그를 추출합니다.
    * (백그라운드) `config.py`에 설정된 백엔드 URL로 `COMPLETE` 상태 콜백(점수, 로그 포함)을 보냅니다.
    * (백그라운드) `grading_temp/` 임시 폴더를 삭제합니다.

---

## 🛠️ 주요 기술 스택

* **Framework**: FastAPI
* **Server**: Uvicorn
* **Async HTTP**: AIOHTTP (백엔드로의 콜백을 위해 사용)
* **Config**: Pydantic

---

## 🔑 핵심 로직

* **`POST /evaluate` (main.py)**
    * 백엔드로부터 `submissionId`와 원본 파일 경로(`filePath`)를 받습니다.
    * 보안을 위해 `filePath`에서 파일 이름만 추출(`os.path.basename`)하여 `config.py`의 `upload_base_dir`와 조합해 **안전한 파일 경로(`secure_file_path`)**를 확정합니다.
    * `background_tasks.add_task`를 사용해 `run_evaluation_task` 함수를 즉시 백그라운드에서 실행시킵니다.
* **`grade_submission` (main.py)**
    * 학생의 zip 파일을 `grading_temp/{submission_id}`에 압축 해제합니다.
    * `asyncio.create_subprocess_shell`을 사용해 `python grading_script.py`를 실행합니다.
    * `asyncio.wait_for`를 통해 600초(10분) 타임아웃을 적용합니다.
    * 프로세스 종료 후 `stdout`을 `json.loads`로 파싱하여 `score`와 `log`를 얻습니다.
* **`grading_script.py`**
    * 실제 채점 로직이 들어가는 파일입니다.
    * **반드시** 최종 결과를 `{"score": 88.8, "log": "채점 로그..."}` 형식의 JSON 문자열로 `print` (stdout)해야 합니다.
    * (현재는 점수 88.8을 반환하는 더미 스크립트입니다.)

---

## ⚙️ 설정 및 실행

### 1. 설정

`config.py` 파일은 `APP_ENV` 환경 변수에 따라 설정을 분리합니다. (`local` 또는 `prod`)

* **`spring_callback_url`**: 백엔드의 채점 완료 콜백 주소 (예: `http://127.0.0.1:18080/api/internal/submissions/{submissionId}/complete`)
* **`spring_status_update_url`**: 백엔드의 채점 시작 콜백 주소 (예: `http://127.0.0.1:18080/api/internal/submissions/{submissionId}/running`)
* **`upload_base_dir`**: 백엔드 서버가 학생의 zip 파일을 저장하는 **절대 경로** (예: `/home/ubuntu/ai-evaluator-be/uploads`)
* **`secret_dataset_path`**: 채점에 사용할 비공개 데이터셋의 경로 (예: `/home/ubuntu/secret_dataset/mnist_test.csv`)

### 2. 실행

1.  **의존성 설치**
    ```bash
    pip install -r requirements.txt
    ```

2.  **개발 서버 실행**
    ```bash
    # local 모드로 실행 (기본값)
    uvicorn main:app --reload --port 8000
    ```

3.  **프로덕션 서버 실행**
    ```bash
    # prod 모드로 실행
    APP_ENV=prod uvicorn main:app --host 0.0.0.0 --port 18000
    ```
