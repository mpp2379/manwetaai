from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import os
import uuid
import json
from dotenv import load_dotenv

from comfyapi.serverless_api import ServerlessAPIClient, prepare_workflow
from auth.routes import auth_bp, login_required

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
app.register_blueprint(auth_bp)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "static", "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
REMOTE_IMAGE_NAME = os.getenv("RUNPOD_REMOTE_IMAGE_NAME", "image.png")

serverless_client = None
if RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID:
    serverless_client = ServerlessAPIClient(RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID)


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    user, _ = __import__("auth.routes", fromlist=["current_identity"]).current_identity()
    message = None
    outputs = []

    if request.method == "POST":
        if not serverless_client:
            message = "Error: Serverless API not configured."
            return render_template("index.html", message=message, outputs=outputs, user=user)

        prompt = request.form.get("prompt") or ""
        width = request.form.get("width") or None
        height = request.form.get("height") or None
        fps = request.form.get("fps") or None
        duration = request.form.get("duration") or None
        seed = request.form.get("seed") or None
        image_file = request.files.get("image")

        try:
            if not image_file or not image_file.filename:
                message = "Error: Image file is required"
                return render_template("index.html", message=message, outputs=outputs, user=user)

            filename = secure_filename(image_file.filename)
            saved_name = f"{uuid.uuid4().hex}_{filename}"
            local_image_path = os.path.join(UPLOAD_DIR, saved_name)
            image_file.save(local_image_path)

            workflow_path = os.path.join(BASE_DIR, "comfyapi", "workflow.json")
            with open(workflow_path, "r", encoding="utf-8") as wf:
                workflow = json.load(wf)

            image_b64 = ServerlessAPIClient.encode_image(local_image_path)
            images = [{"name": REMOTE_IMAGE_NAME, "image": image_b64}]

            workflow = prepare_workflow(
                workflow=workflow,
                image_filename=REMOTE_IMAGE_NAME,
                prompt=prompt,
                width=width,
                height=height,
                fps=fps,
                duration=duration,
                seed=seed if seed not in [None, ""] else None,
            )

            result = serverless_client.submit_workflow(workflow, images)
            run_id = result.get("id")
            if not run_id:
                message = f"Error: No run ID in response. Response: {result}"
                return render_template("index.html", message=message, outputs=outputs, user=user)

            message = f"Job submitted (Run ID: {run_id}). Processing..."
            return render_template(
                "index.html", message=message, outputs=outputs,
                run_id=run_id, user=user
            )

        except Exception as e:
            message = f"Error: {str(e)}"
            import traceback
            print(traceback.format_exc(), flush=True)

    return render_template("index.html", message=message, outputs=outputs, user=user)


@app.route("/status")
@login_required
def status():
    run_id = request.args.get("run_id")
    if not run_id:
        return {"error": "Missing run_id"}, 400
    if not serverless_client:
        return {"status": "error", "detail": "Serverless API not configured"}, 500

    try:
        status_result = serverless_client.get_status(run_id)
        status_value = status_result.get("status")

        if status_value == "COMPLETED":
            outputs = ServerlessAPIClient.extract_outputs(status_result)
            saved_outputs = []
            for output in outputs:
                if output.get("data") or output.get("url"):
                    try:
                        output_filename = secure_filename(output.get("filename", "output.bin"))
                        output_path = os.path.join(OUTPUT_DIR, output_filename)
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        ServerlessAPIClient.save_output_file(output, output_path)
                        saved_outputs.append({
                            "filename": f"outputs/{output_filename}",
                            "type": output.get("type", "file")
                        })
                    except Exception as e:
                        print(f"Error saving output: {e}", flush=True)
            return {"status": "completed", "outputs": saved_outputs}

        if status_value == "FAILED":
            return {"status": "error", "detail": status_result.get("error", "Unknown error")}

        return {"status": status_value.lower() if status_value else "running"}

    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    print("FLASK APP STARTED", flush=True)
    print("RUNPOD ENDPOINT:", repr(RUNPOD_ENDPOINT_ID), flush=True)
    app.run(host="127.0.0.1", port=5555, debug=False)
