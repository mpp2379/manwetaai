import json
import os
import random
import time


# ============================================================
# AD GENERATION SERVICE
#
# Owns the product-advertisement generation flow:
#   template + variables -> final prompt -> Qwen workflow
#   -> RunPod serverless submission.
#
# Reuses the existing RunPod ServerlessAPIClient; the Qwen
# technical settings live in the model profile and workflow
# JSON, never inside templates.
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PROJECT_DIR = os.path.dirname(BASE_DIR)

WORKFLOWS_DIR = os.path.join(
    PROJECT_DIR,
    "comfyapi"
)


class AdGenerationError(RuntimeError):
    pass


def _load_workflow(workflow_name):

    path = os.path.join(
        WORKFLOWS_DIR,
        f"{workflow_name}.json"
    )

    if not os.path.isfile(path):

        raise AdGenerationError(
            f"Workflow '{workflow_name}' not found "
            f"for the selected model profile."
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_qwen_edit_workflow(
    workflow,
    model_profile,
    prompt=None,
    image_filename=None,
    seed=None
):

    """
    Inject the resolved prompt / reference image / seed into
    the Qwen Image Edit workflow using node ids from the
    model profile.
    """

    nodes = model_profile.get("nodes") or {}

    load_image_node = nodes.get("loadImage")
    positive_node = nodes.get("positivePrompt")
    negative_node = nodes.get("negativePrompt")
    sampler_node = nodes.get("sampler")

    try:

        if image_filename and load_image_node:
            workflow[load_image_node]["inputs"]["image"] = (
                image_filename
            )

        if prompt is not None and positive_node:
            workflow[positive_node]["inputs"]["prompt"] = prompt

        if negative_node and negative_node in workflow:
            # Keep the dedicated negative prompt node empty;
            # the positive node above carries the full edit
            # instruction (Qwen Image Edit pattern).
            pass

        if seed is None:
            seed = random.randint(0, 2**63 - 1)

        if sampler_node:
            workflow[sampler_node]["inputs"]["seed"] = int(seed)

    except KeyError as e:

        raise AdGenerationError(
            f"Workflow node missing expected input: {e}"
        ) from e

    print(
        "\nProduct ad workflow parameters:",
        f"  Image  : {image_filename}",
        f"  Prompt : {prompt[:120]}...",
        f"  Seed   : {seed}",
        sep="\n",
        flush=True
    )

    return workflow


def generate_ad(
    serverless_client,
    template,
    model_profile,
    prompt,
    image_path
):

    """
    Submit a product-ad generation job.

    Returns dict with run_id, prompt and timing metadata.
    Raises AdGenerationError on failure.
    """

    from comfyapi.serverless_api import ServerlessAPIClient

    if not serverless_client:

        raise AdGenerationError(
            "Serverless API is not configured. "
            "Check RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID."
        )

    started = time.time()

    try:

        workflow = _load_workflow(
            model_profile["workflow"]
        )

        remote_image_name = model_profile.get(
            "remoteImageName",
            "image.png"
        )

        image_b64 = ServerlessAPIClient.encode_image(
            image_path
        )

        images = [
            {
                "name": remote_image_name,
                "image": image_b64
            }
        ]

        workflow = prepare_qwen_edit_workflow(
            workflow=workflow,
            model_profile=model_profile,
            prompt=prompt,
            image_filename=remote_image_name
        )

        result = serverless_client.submit_workflow(
            workflow,
            images
        )

    except AdGenerationError:

        raise

    except Exception as e:

        raise AdGenerationError(
            f"ComfyUI generation failed: {e}"
        ) from e

    run_id = result.get("id")

    if not run_id:

        raise AdGenerationError(
            f"No run ID in RunPod response: {result}"
        )

    duration = round(time.time() - started, 2)

    # --------------------------------------------------------
    # REPRODUCIBLE LOGGING
    # --------------------------------------------------------

    print(
        "\n[AD GENERATION]",
        f"  templateId     : {template['id']}",
        f"  modelProfileId : {model_profile['id']}",
        f"  runId          : {run_id}",
        f"  submitDuration : {duration}s",
        f"  prompt         : {prompt}",
        sep="\n",
        flush=True
    )

    return {
        "runId": run_id,
        "templateId": template["id"],
        "modelProfileId": model_profile["id"],
        "resolvedPrompt": prompt,
        "submitDurationSeconds": duration
    }
