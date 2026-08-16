# ComfyUI Client App

Flask front-end for submitting an image + LTX/video prompt to a running ComfyUI instance using the `comfyapi` helper.

Prerequisites:
- A running ComfyUI server with the API enabled (e.g. `http://localhost:8188`).

## Run

```bash
python -m venv venv
# Windows
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 and enter your ComfyUI base URL, upload an image, set a prompt and parameters, then submit.
