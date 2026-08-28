from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

import os
import uuid
import json
import traceback

from dotenv import load_dotenv

from comfyapi.serverless_api import (
    ServerlessAPIClient,
    prepare_workflow,
    prepare_character_workflow
)

from comfyapi.character_prompt import build_character_prompt

from auth.routes import (
    auth_bp,
    login_required
)

from story.generator import generate_story

from services.template_service import (
    get_categories,
    get_templates,
    get_template,
    get_model_profile,
    get_prompt_library
)

from services.prompt_builder import build_prompt, PromptBuildError

from services.ad_generation_service import (
    generate_ad,
    AdGenerationError
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "dev-only-change-me"
)

app.register_blueprint(auth_bp)


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_DIR = os.path.join(
    BASE_DIR,
    "static",
    "uploads"
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "static",
    "outputs"
)

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# ============================================================
# RUNPOD CONFIGURATION
# ============================================================

RUNPOD_API_KEY = os.getenv(
    "RUNPOD_API_KEY"
)

RUNPOD_ENDPOINT_ID = os.getenv(
    "RUNPOD_ENDPOINT_ID"
)

REMOTE_IMAGE_NAME = os.getenv(
    "RUNPOD_REMOTE_IMAGE_NAME",
    "image.png"
)


serverless_client = None


if RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID:

    serverless_client = ServerlessAPIClient(
        RUNPOD_API_KEY,
        RUNPOD_ENDPOINT_ID
    )


# ============================================================
# HELPER: CURRENT USER
# ============================================================

def get_current_user():

    try:

        result = __import__(
            "auth.routes",
            fromlist=["current_identity"]
        ).current_identity()

        # No authenticated user
        if result is None:
            return None

        # If current_identity() returns
        # (user, something_else)
        if isinstance(result, tuple):

            if len(result) == 0:
                return None

            return result[0]

        # If current_identity() directly returns user
        return result

    except Exception as e:

        print(
            f"Error getting current user: {e}",
            flush=True
        )

        return None


# ============================================================
# HOME / LOGIN / WORKSPACE
# ============================================================

@app.route("/")
def home():

    user = get_current_user()

    return render_template(
        "login.html",
        user=user
    )


# ============================================================
# VIDEO GENERATOR
#
# IMPORTANT:
# Previously this was "/".
# It is now "/video".
# ============================================================

@app.route(
    "/video",
    methods=["GET", "POST"]
)
@login_required
def index():

    user = get_current_user()

    message = None
    outputs = []

    if request.method == "POST":

        if not serverless_client:

            message = (
                "Error: Serverless API not configured."
            )

            return render_template(
                "index.html",
                message=message,
                outputs=outputs,
                user=user
            )

        prompt = (
            request.form.get("prompt")
            or ""
        )

        width = (
            request.form.get("width")
            or None
        )

        height = (
            request.form.get("height")
            or None
        )

        fps = (
            request.form.get("fps")
            or None
        )

        duration = (
            request.form.get("duration")
            or None
        )

        seed = (
            request.form.get("seed")
            or None
        )

        image_file = request.files.get(
            "image"
        )

        try:

            # ------------------------------------------------
            # IMAGE VALIDATION
            # ------------------------------------------------

            if (
                not image_file
                or not image_file.filename
            ):

                message = (
                    "Error: Image file is required"
                )

                return render_template(
                    "index.html",
                    message=message,
                    outputs=outputs,
                    user=user
                )


            # ------------------------------------------------
            # SAVE IMAGE
            # ------------------------------------------------

            filename = secure_filename(
                image_file.filename
            )

            saved_name = (
                f"{uuid.uuid4().hex}_{filename}"
            )

            local_image_path = os.path.join(
                UPLOAD_DIR,
                saved_name
            )

            image_file.save(
                local_image_path
            )


            # ------------------------------------------------
            # LOAD COMFYUI WORKFLOW
            # ------------------------------------------------

            workflow_path = os.path.join(
                BASE_DIR,
                "comfyapi",
                "workflow.json"
            )

            with open(
                workflow_path,
                "r",
                encoding="utf-8"
            ) as wf:

                workflow = json.load(wf)


            # ------------------------------------------------
            # ENCODE IMAGE
            # ------------------------------------------------

            image_b64 = (
                ServerlessAPIClient.encode_image(
                    local_image_path
                )
            )

            images = [
                {
                    "name": REMOTE_IMAGE_NAME,
                    "image": image_b64
                }
            ]


            # ------------------------------------------------
            # PREPARE WORKFLOW
            # ------------------------------------------------

            workflow = prepare_workflow(
                workflow=workflow,
                image_filename=REMOTE_IMAGE_NAME,
                prompt=prompt,
                width=width,
                height=height,
                fps=fps,
                duration=duration,
                seed=(
                    seed
                    if seed not in [None, ""]
                    else None
                )
            )


            # ------------------------------------------------
            # SUBMIT RUNPOD JOB
            # ------------------------------------------------

            result = (
                serverless_client.submit_workflow(
                    workflow,
                    images
                )
            )

            run_id = result.get("id")


            if not run_id:

                message = (
                    "Error: No run ID in response. "
                    f"Response: {result}"
                )

                return render_template(
                    "index.html",
                    message=message,
                    outputs=outputs,
                    user=user
                )


            # ------------------------------------------------
            # JOB SUBMITTED
            # ------------------------------------------------

            message = (
                f"Job submitted "
                f"(Run ID: {run_id}). "
                f"Processing..."
            )

            return render_template(
                "index.html",
                message=message,
                outputs=outputs,
                run_id=run_id,
                user=user
            )


        except Exception as e:

            message = (
                f"Error: {str(e)}"
            )

            print(
                traceback.format_exc(),
                flush=True
            )


    return render_template(
        "index.html",
        message=message,
        outputs=outputs,
        user=user
    )


# ============================================================
# RUNPOD STATUS
# ============================================================

@app.route("/status")
@login_required
def status():

    run_id = request.args.get(
        "run_id"
    )


    if not run_id:

        return {
            "error": "Missing run_id"
        }, 400


    if not serverless_client:

        return {
            "status": "error",
            "detail": (
                "Serverless API not configured"
            )
        }, 500


    try:

        status_result = (
            serverless_client.get_status(
                run_id
            )
        )

        status_value = (
            status_result.get("status")
        )


        # ====================================================
        # COMPLETED
        # ====================================================

        if status_value == "COMPLETED":

            outputs = (
                ServerlessAPIClient.extract_outputs(
                    status_result
                )
            )

            saved_outputs = []


            for output in outputs:

                if (
                    output.get("data")
                    or output.get("url")
                ):

                    try:

                        output_filename = (
                            f"{uuid.uuid4().hex}_"
                            + secure_filename(
                                output.get(
                                    "filename",
                                    "output.bin"
                                )
                            )
                        )

                        output_path = os.path.join(
                            OUTPUT_DIR,
                            output_filename
                        )

                        os.makedirs(
                            os.path.dirname(
                                output_path
                            ),
                            exist_ok=True
                        )

                        (
                            ServerlessAPIClient
                            .save_output_file(
                                output,
                                output_path
                            )
                        )

                        saved_outputs.append(
                            {
                                "filename":
                                    f"outputs/{output_filename}",

                                "type":
                                    output.get(
                                        "type",
                                        "file"
                                    )
                            }
                        )


                    except Exception as e:

                        print(
                            f"Error saving output: {e}",
                            flush=True
                        )


            return {
                "status": "completed",
                "outputs": saved_outputs
            }


        # ====================================================
        # FAILED
        # ====================================================

        if status_value == "FAILED":

            return {
                "status": "error",
                "detail":
                    status_result.get(
                        "error",
                        "Unknown error"
                    )
            }


        # ====================================================
        # RUNNING
        # ====================================================

        return {
            "status":
                (
                    status_value.lower()
                    if status_value
                    else "running"
                )
        }


    except Exception as e:

        return {
            "status": "error",
            "detail": str(e)
        }, 500


# ============================================================
# CHARACTER GENERATOR (Flux 1 Schnell)
# ============================================================

@app.route(
    "/character",
    methods=["GET", "POST"]
)
@login_required
def character():

    user = get_current_user()

    message = None

    if request.method == "POST":

        if not serverless_client:

            message = (
                "Error: Serverless API not configured."
            )

            return render_template(
                "character.html",
                message=message,
                user=user,
                **request.form
            )

        # ----------------------------------------------------
        # READ FORM INPUTS
        # ----------------------------------------------------

        form = request.form

        gender = form.get("gender", "").strip()
        age = form.get("age", "").strip()
        ethnicity = form.get("ethnicity", "").strip()

        face_shape = form.get("face_shape", "").strip()
        eye_color = form.get("eye_color", "").strip()
        eye_shape = form.get("eye_shape", "").strip()
        face_details = form.get("face_details", "").strip()
        distinctive_marks = (
            form.get("distinctive_marks", "").strip()
        )

        hair = form.get("hair", "").strip()
        body = form.get("body", "").strip()
        clothing = form.get("clothing", "").strip()
        expression = form.get("expression", "").strip()
        visual_style = form.get("visual_style", "").strip()
        extra_details = form.get("extra_details", "").strip()

        width = form.get("width") or 1024
        height = form.get("height") or 1024
        seed = form.get("seed") or None

        try:

            # ------------------------------------------------
            # VALIDATION
            # ------------------------------------------------

            if not any(
                (
                    gender,
                    age,
                    ethnicity,
                    face_shape,
                    eye_color,
                    eye_shape,
                    face_details,
                    distinctive_marks,
                    hair,
                    clothing,
                    expression,
                    extra_details
                )
            ):

                message = (
                    "Error: Please describe your character "
                    "using at least one field."
                )

                return render_template(
                    "character.html",
                    message=message,
                    user=user,
                    **form
                )

            width = int(width)
            height = int(height)

            if width < 256 or width > 2048:
                raise ValueError(
                    "Width must be between 256 and 2048 px."
                )

            if height < 256 or height > 2048:
                raise ValueError(
                    "Height must be between 256 and 2048 px."
                )

            if seed in [None, ""]:
                seed = None

            # ------------------------------------------------
            # BUILD IMAGE GENERATION PROMPT
            # ------------------------------------------------

            prompt = build_character_prompt(

                gender=gender,

                age=age,

                ethnicity=ethnicity,

                face_shape=face_shape,

                eye_color=eye_color,

                eye_shape=eye_shape,

                face_details=face_details,

                distinctive_marks=distinctive_marks,

                hair=hair,

                body=body,

                clothing=clothing,

                expression=expression,

                visual_style=visual_style,

                extra_details=extra_details
            )

            # ------------------------------------------------
            # LOAD COMFYUI WORKFLOW
            # ------------------------------------------------

            workflow_path = os.path.join(
                BASE_DIR,
                "comfyapi",
                "character_workflow.json"
            )

            with open(
                workflow_path,
                "r",
                encoding="utf-8"
            ) as wf:

                workflow = json.load(wf)

            # ------------------------------------------------
            # PREPARE WORKFLOW
            # ------------------------------------------------

            workflow = prepare_character_workflow(

                workflow=workflow,

                prompt=prompt,

                width=width,

                height=height,

                seed=seed
            )

            # ------------------------------------------------
            # SUBMIT RUNPOD JOB
            # (text-to-image: no input images needed)
            # ------------------------------------------------

            result = (
                serverless_client.submit_workflow(
                    workflow
                )
            )

            run_id = result.get("id")

            if not run_id:

                message = (
                    "Error: No run ID in response. "
                    f"Response: {result}"
                )

                return render_template(
                    "character.html",
                    message=message,
                    user=user,
                    **form
                )

            # ------------------------------------------------
            # JOB SUBMITTED
            # ------------------------------------------------

            message = (
                f"Job submitted "
                f"(Run ID: {run_id}). "
                f"Generating character..."
            )

            return render_template(
                "character.html",
                message=message,
                user=user,
                run_id=run_id,
                **form
            )

        except ValueError as e:

            message = f"Error: {str(e)}"

        except Exception as e:

            message = f"Error: {str(e)}"

            print(
                traceback.format_exc(),
                flush=True
            )

    return render_template(
        "character.html",
        message=message,
        user=user
    )


# ============================================================
# PRODUCT ADS
#
# Creative Template Library — MVP category: product_ads
# Flow: upload product image -> pick template -> backend
# builds prompt -> Qwen Image Edit -> poll existing /status.
# ============================================================

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@app.route("/product-ads")
@login_required
def product_ads_page():

    user = get_current_user()

    # Product Ads uses the prompt-library subcategories as the
    # user-facing categories. Curated product templates are mapped
    # to Product & Brand by template_service.
    templates = get_templates("product_ads")

    category_defs = [
        {
            "id": "product_brand",
            "name": "Product & Brand",
            "description": "Premium product photography, branding and commercial product shots.",
        },
        {
            "id": "food_drink",
            "name": "Food & Drink",
            "description": "Food, beverage and appetizing commercial advertising scenes.",
        },
        {
            "id": "poster_campaign",
            "name": "Poster & Campaign",
            "description": "Campaign creatives, promotional posters and advertising compositions.",
        },
    ]

    for category in category_defs:
        category["count"] = sum(
            1 for t in templates
            if t.get("subcategoryId") == category["id"]
        )

    return render_template(
        "product_ads.html",
        user=user,
        categories=category_defs,
        templates=templates
    )


@app.get("/api/ads/categories")
@login_required
def ads_categories_api():

    templates = get_templates("product_ads")

    categories = [
        {
            "id": "product_brand",
            "name": "Product & Brand",
            "description": "Premium product photography, branding and commercial product shots.",
        },
        {
            "id": "food_drink",
            "name": "Food & Drink",
            "description": "Food, beverage and appetizing commercial advertising scenes.",
        },
        {
            "id": "poster_campaign",
            "name": "Poster & Campaign",
            "description": "Campaign creatives, promotional posters and advertising compositions.",
        },
    ]

    for category in categories:
        category["count"] = sum(
            1 for t in templates
            if t.get("subcategoryId") == category["id"]
        )

    return {"categories": categories}


@app.get("/api/templates")
@login_required
def templates_api():

    category = request.args.get("category")
    subcategory = request.args.get("subcategory")

    try:

        templates = get_templates(category)

        if subcategory:
            templates = [
                t for t in templates
                if t.get("subcategoryId") == subcategory
            ]

    except Exception as e:

        print(
            traceback.format_exc(),
            flush=True
        )

        return {"error": str(e)}, 500

    return {
        "templates": [
            {
                "id": t["id"],
                "categoryId": t["categoryId"],
                "subcategoryId": t.get("subcategoryId"),
                "name": t["name"],
                "description": t["description"],
                "thumbnail": t.get("thumbnail"),
                "variables": t.get("variables", {}),
                "origin": t.get("origin", "curated")
            }
            for t in templates
        ]
    }


@app.post("/api/ads/generate")
@login_required
def ads_generate_api():

    user = get_current_user()

    # --------------------------------------------------------
    # READ REQUEST (multipart: image file + template id)
    # --------------------------------------------------------

    template_id = (
        request.form.get("templateId")
        or ""
    ).strip()

    subcategory_id = (
        request.form.get("subcategoryId")
        or ""
    ).strip()

    product_image = request.files.get("productImage")

    # Any extra form fields are treated as template-variable
    # values (e.g. surface / lighting, or future library
    # variables). Values are capped for safety.
    reserved = {"templateId", "subcategoryId", "productImage"}

    overrides = {
        key: value[:400]
        for key, value in request.form.items()
        if key not in reserved
        and value
        and value.strip()
    }


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not template_id:

        return {
            "error": "templateId is required."
        }, 400

    if (
        not product_image
        or not product_image.filename
    ):

        return {
            "error": "Product image is required."
        }, 400

    template = get_template(template_id)

    if not template:

        return {
            "error": f"Template '{template_id}' "
                     f"was not found."
        }, 404

    if not template.get("enabled"):

        return {
            "error": f"Template '{template_id}' "
                     f"is disabled."
        }, 400

    # The selected template must belong to the category shown in the UI.
    # This prevents a client from bypassing the category/template flow.
    if subcategory_id and template.get("subcategoryId") != subcategory_id:

        return {
            "error": "Selected template does not belong to the chosen category."
        }, 400

    model_profile = get_model_profile(
        template["modelProfileId"]
    )

    if not model_profile or not model_profile.get("enabled"):

        return {
            "error": "Model profile for this template "
                     "is not available."
        }, 500

    extension = os.path.splitext(
        secure_filename(product_image.filename)
    )[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:

        return {
            "error": "Unsupported image type. Use PNG, JPG or WEBP."
        }, 400


    # --------------------------------------------------------
    # SAVE PRODUCT IMAGE
    # --------------------------------------------------------

    saved_name = (
        f"{uuid.uuid4().hex}_"
        + secure_filename(product_image.filename)
    )

    local_image_path = os.path.join(
        UPLOAD_DIR,
        saved_name
    )

    product_image.save(local_image_path)


    # --------------------------------------------------------
    # BUILD PROMPT (backend owns prompt construction)
    # --------------------------------------------------------

    try:

        final_prompt = build_prompt(
            template=template,
            product_data=None,
            options=overrides
        )

    except PromptBuildError as e:

        return {"error": str(e)}, 400


    # --------------------------------------------------------
    # SUBMIT GENERATION
    # --------------------------------------------------------

    try:

        result = generate_ad(
            serverless_client=serverless_client,
            template=template,
            model_profile=model_profile,
            prompt=final_prompt,
            image_path=local_image_path
        )

    except AdGenerationError as e:

        print(
            traceback.format_exc(),
            flush=True
        )

        return {"error": str(e)}, 502

    return {
        "success": True,
        "jobId": result["runId"],
        "runId": result["runId"],
        "templateId": template["id"]
    }


@app.route("/story")
@login_required
def story_page():

    user = get_current_user()

    return render_template(
        "story.html",
        user=user
    )


# ============================================================
# STORY GENERATION API
# ============================================================

@app.post("/api/story/generate")
@login_required
def generate_story_api():

    try:

        # ----------------------------------------------------
        # READ REQUEST
        # ----------------------------------------------------

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        # ----------------------------------------------------
        # USER INPUT
        # ----------------------------------------------------

        idea = (
            data.get("idea", "")
            .strip()
        )

        duration = (
            data.get("duration")
        )


        # ----------------------------------------------------
        # VALIDATE IDEA
        # ----------------------------------------------------

        if not idea:

            return {
                "error":
                    "Story idea is required."
            }, 400


        # ----------------------------------------------------
        # VALIDATE DURATION
        # ----------------------------------------------------

        if not duration:

            return {
                "error":
                    "Duration is required."
            }, 400


        duration = int(duration)


        if duration < 5 or duration > 180:

            return {
                "error":
                    "Duration must be between "
                    "5 and 180 seconds."
            }, 400


        # ----------------------------------------------------
        # GENERATE STORY
        # ----------------------------------------------------

        story = generate_story(

            idea=idea,

            duration=duration,

            language=data.get(
                "language",
                "Hindi"
            ),

            characters=data.get(
                "characters",
                ""
            ),

            character_descriptions=data.get(
                "character_descriptions",
                ""
            ),

            location=data.get(
                "location",
                ""
            ),

            visual_style=data.get(
                "visual_style",
                ""
            ),

            tone=data.get(
                "tone",
                ""
            ),

            audience=data.get(
                "audience",
                ""
            ),

            requirements=data.get(
                "requirements",
                ""
            )
        )


        # ====================================================
        # IMPORTANT
        #
        # generate_story() can internally contain:
        #
        #   user_story
        #   image_generation
        #   video_generation
        #   validation
        #
        # The browser should ONLY receive user_story.
        # ====================================================

        if isinstance(story, dict):

            if "user_story" in story:

                return {
                    "success": True,
                    "story": story["user_story"]
                }


            # Backward compatibility:
            # If generator already returns only
            # user-facing story JSON.

            return {
                "success": True,
                "story": story
            }


        return {
            "success": True,
            "story": story
        }


    except Exception as e:

        print(
            traceback.format_exc(),
            flush=True
        )

        return {
            "error": str(e)
        }, 500


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print(
        "FLASK APP STARTED",
        flush=True
    )

    print(
        "RUNPOD ENDPOINT:",
        repr(RUNPOD_ENDPOINT_ID),
        flush=True
    )

    print(
        "HOME: http://127.0.0.1:5555/",
        flush=True
    )

    print(
        "VIDEO: http://127.0.0.1:5555/video",
        flush=True
    )

    print(
        "CHARACTER: http://127.0.0.1:5555/character",
        flush=True
    )

    print(
        "STORY: http://127.0.0.1:5555/story",
        flush=True
    )

    app.run(
        host="127.0.0.1",
        port=5555,
        debug=False
    )