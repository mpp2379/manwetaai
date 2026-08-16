import base64
import json
import os
import time
import uuid
from pathlib import Path

import requests


# ============================================================
# RunPod Serverless API Client
# ============================================================

class ServerlessAPIClient:
    """
    Client for RunPod Serverless API endpoints.
    Provides similar interface to ComfyUIClient but uses RunPod's API.
    """

    def __init__(self, api_key: str, endpoint_id: str):
        """
        Initialize the serverless API client.
        
        Args:
            api_key: RunPod API key
            endpoint_id: RunPod endpoint ID
        """
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"
        self.run_url = f"{self.base_url}/run"
        self.status_url = f"{self.base_url}/status"

    # --------------------------------------------------------
    # Submit workflow (synchronous)
    # --------------------------------------------------------

    def submit_workflow(self, workflow, images=None):
        """
        Submit a workflow to RunPod Serverless API.
        
        Args:
            workflow: The ComfyUI workflow dict
            images: List of dicts with 'name' and 'image' (base64) keys
        
        Returns:
            dict: The response from RunPod API
        """
        print("[1/3] Preparing RunPod request...")

        payload = {
            "input": {
                "workflow": workflow,
            }
        }

        # Add images if provided
        if images:
            payload["input"]["images"] = images

        print("[2/3] Submitting to serverless endpoint...")

        try:
            response = requests.post(
                self.run_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=1800,  # 30 minutes timeout
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Request failed before reaching RunPod: {exc}"
            ) from exc

        if response.status_code >= 400:
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text

            print(f"RunPod returned error: {response.status_code}")
            print(json.dumps(error_data, indent=2) if isinstance(error_data, dict) else error_data)
            
            raise RuntimeError(
                f"RunPod request failed with status {response.status_code}: {error_data}"
            )

        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("Response from RunPod was not valid JSON")

        print("[3/3] Response received successfully")
        return result

    # --------------------------------------------------------
    # Get status
    # --------------------------------------------------------

    def get_status(self, run_id):
        """
        Get the status of a submitted run.
        Uses the /status/{run_id} endpoint from RunPod.
        
        Args:
            run_id: The run ID from submit_workflow response
        
        Returns:
            dict: Status information
        """
        # RunPod status endpoint format: /v2/{endpoint_id}/status/{run_id}
        url = f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{run_id}"
        
        try:
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Status check failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                error_data = response.json()
            except:
                error_data = response.text
            raise RuntimeError(
                f"Failed to get status: {response.status_code} - {error_data}"
            )

        return response.json()

    # --------------------------------------------------------
    # Encode image to base64
    # --------------------------------------------------------

    @staticmethod
    def encode_image(image_path: str) -> str:
        """
        Encode an image file to base64 string.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            str: Base64 encoded image data
        """
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        print(f"[1/4] Encoding image: {image_path.name}")

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        size_mb = len(image_b64) / 1024 / 1024
        print(f"      Encoded size: {size_mb:.2f} MB")

        return image_b64

    # --------------------------------------------------------
    # Extract output files from response
    # --------------------------------------------------------

    @staticmethod
    def extract_outputs(result: dict) -> list:
        """
        Extract output files from RunPod API response.
        
        Args:
            result: Response from RunPod API
        
        Returns:
            list: List of output file info dicts
        """
        outputs = []

        # Check if result has the expected structure
        output_data = result.get("output", {})
        
        # Extract images
        for item in output_data.get("images", []):
            outputs.append({
                "filename": item.get("filename", "image.png"),
                "type": "image",
                "data": item.get("data"),  # Could be base64 or URL
                "url": item.get("url"),
            })

        # Extract videos
        for item in output_data.get("videos", []):
            outputs.append({
                "filename": item.get("filename", "video.mp4"),
                "type": "video",
                "data": item.get("data"),  # Could be base64 or URL
                "url": item.get("url"),
            })

        # Extract generic files
        for item in output_data.get("files", []):
            outputs.append({
                "filename": item.get("filename", "file.bin"),
                "type": "file",
                "data": item.get("data"),  # Could be base64 or URL
                "url": item.get("url"),
            })

        return outputs

    # --------------------------------------------------------
    # Save output file
    # --------------------------------------------------------

    @staticmethod
    def save_output_file(file_info: dict, output_path: str) -> Path:
        """
        Save an output file from RunPod response.
        
        Args:
            file_info: File info dict from extract_outputs
            output_path: Path where to save the file
        
        Returns:
            Path: Path to saved file
        """
        output_path = Path(output_path)
        filename = file_info.get("filename", "output.bin")

        print(f"[4/4] Saving: {filename}")

        # Check if we have base64 data
        if file_info.get("data"):
            with open(output_path, "wb") as f:
                decoded_data = base64.b64decode(file_info["data"])
                f.write(decoded_data)
        # Check if we have a URL
        elif file_info.get("url"):
            response = requests.get(file_info["url"], stream=True, timeout=120)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        else:
            raise ValueError(f"No data or URL found for file: {filename}")

        print(f"      Saved: {output_path}")

        return output_path


# ============================================================
# Workflow modifications (same as before)
# ============================================================

def prepare_workflow(
    workflow,
    image_filename=None,
    prompt=None,
    width=None,
    height=None,
    fps=None,
    duration=None,
    seed=None
):
    """
    Modify workflow with user-provided parameters.
    """
    import random

    # --------------------------------------------------------
    # Image
    # Node 269 = LoadImage
    # --------------------------------------------------------

    if image_filename:
        workflow["269"]["inputs"]["image"] = image_filename

    # --------------------------------------------------------
    # Prompt
    # Node 320:319 = PrimitiveStringMultiline
    # --------------------------------------------------------

    if prompt is not None:
        workflow["320:319"]["inputs"]["value"] = prompt

    # --------------------------------------------------------
    # Width
    # Node 320:312
    # --------------------------------------------------------

    if width is not None:
        workflow["320:312"]["inputs"]["value"] = int(width)

    # --------------------------------------------------------
    # Height
    # Node 320:299
    # --------------------------------------------------------

    if height is not None:
        workflow["320:299"]["inputs"]["value"] = int(height)

    # --------------------------------------------------------
    # FPS
    # Node 320:300
    # --------------------------------------------------------

    if fps is not None:
        workflow["320:300"]["inputs"]["value"] = int(fps)

    # --------------------------------------------------------
    # Duration
    # Node 320:301
    # --------------------------------------------------------

    if duration is not None:
        workflow["320:301"]["inputs"]["value"] = int(duration)

    # --------------------------------------------------------
    # Random noise seeds
    # Nodes 320:276 and 320:277
    # --------------------------------------------------------

    if seed is None:
        seed = random.randint(0, 2**63 - 1)

    workflow["320:276"]["inputs"]["noise_seed"] = seed
    workflow["320:277"]["inputs"]["noise_seed"] = seed

    print("\nWorkflow parameters:")
    print(f"  Image    : {image_filename}")
    print(f"  Prompt   : {prompt}")
    print(f"  Width    : {width}")
    print(f"  Height   : {height}")
    print(f"  FPS      : {fps}")
    print(f"  Duration : {duration}")
    print(f"  Seed     : {seed}")

    return workflow
