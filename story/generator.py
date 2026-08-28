import json
import os

from openai import OpenAI

from story.prompt import STORY_ARCHITECT_PROMPT


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def generate_story(
    idea,
    duration,
    language="Hindi",
    characters="",
    character_descriptions="",
    location="",
    visual_style="",
    tone="",
    audience="",
    requirements=""
):

    # ============================================================
    # USER INPUT
    # ============================================================

    user_input = f"""
USER IDEA:
{idea}

DURATION_SECONDS:
{duration}

LANGUAGE:
{language}

CHARACTERS:
{characters}

CHARACTER_DESCRIPTIONS:
{character_descriptions}

LOCATION:
{location}

VISUAL_STYLE:
{visual_style}

TONE:
{tone}

TARGET_AUDIENCE:
{audience}

PLATFORM:
Instagram Reel

SPECIAL_REQUIREMENTS:
{requirements}
"""

    print("\n========== STORY GENERATION ==========")
    print(f"Duration: {duration}s")
    print(f"Language: {language}")
    print(f"Idea: {idea}")
    print("======================================\n")

    # ============================================================
    # OPENAI CALL
    # ============================================================

    response = client.responses.create(
        model="gpt-5-nano",
        instructions=STORY_ARCHITECT_PROMPT,
        input=user_input,
    )

    raw_output = response.output_text.strip()

    # ============================================================
    # LOG RAW GPT RESPONSE
    # ============================================================

    print("\n========== GPT RAW OUTPUT ==========")
    print(raw_output)
    print("====================================\n")

    # ============================================================
    # REMOVE MARKDOWN FENCES
    # ============================================================

    if raw_output.startswith("```"):

        raw_output = raw_output.replace(
            "```json",
            "",
            1
        )

        raw_output = raw_output.replace(
            "```",
            ""
        )

        raw_output = raw_output.strip()

    # ============================================================
    # PARSE JSON
    # ============================================================

    try:

        result = json.loads(raw_output)

    except json.JSONDecodeError as e:

        print(
            "\n========== JSON PARSE ERROR =========="
        )

        print(
            f"Error: {e}"
        )

        print(
            "======================================\n"
        )

        raise ValueError(
            f"GPT did not return valid JSON: {e}"
        )

    # ============================================================
    # VALIDATE
    # ============================================================

    validate_story(
        result,
        int(duration)
    )

    # ============================================================
    # RETURN
    # ============================================================

    return result


# =================================================================
# STORY VALIDATION
# =================================================================

def validate_story(
    result,
    duration
):

    # ============================================================
    # BASIC RESPONSE VALIDATION
    # ============================================================

    if not isinstance(result, dict):

        raise ValueError(
            "GPT response must be a JSON object."
        )


    # ============================================================
    # USER STORY
    # ============================================================

    user_story = result.get(
        "user_story"
    )

    if not isinstance(
        user_story,
        dict
    ):

        raise ValueError(
            "GPT response is missing "
            "the 'user_story' object."
        )


    # ============================================================
    # STORY SCENES
    # ============================================================

    scenes = user_story.get(
        "scenes"
    )

    if not isinstance(
        scenes,
        list
    ) or not scenes:

        raise ValueError(
            "GPT response does not contain "
            "a valid 'user_story.scenes' array."
        )


    # ============================================================
    # IMAGE GENERATION
    # ============================================================

    image_generation = result.get(
        "image_generation"
    )

    if not isinstance(
        image_generation,
        dict
    ):

        raise ValueError(
            "GPT response is missing "
            "the 'image_generation' object."
        )


    image_scenes = image_generation.get(
        "scenes"
    )

    if not isinstance(
        image_scenes,
        list
    ):

        raise ValueError(
            "GPT response does not contain "
            "a valid 'image_generation.scenes' array."
        )


    # ============================================================
    # VIDEO GENERATION
    # ============================================================

    video_generation = result.get(
        "video_generation"
    )

    if not isinstance(
        video_generation,
        dict
    ):

        raise ValueError(
            "GPT response is missing "
            "the 'video_generation' object."
        )


    video_scenes = video_generation.get(
        "scenes"
    )

    if not isinstance(
        video_scenes,
        list
    ):

        raise ValueError(
            "GPT response does not contain "
            "a valid 'video_generation.scenes' array."
        )


    # ============================================================
    # SCENE COUNT VALIDATION
    # ============================================================

    if len(scenes) != len(image_scenes):

        raise ValueError(
            "Scene count mismatch between "
            "user_story and image_generation."
        )


    if len(scenes) != len(video_scenes):

        raise ValueError(
            "Scene count mismatch between "
            "user_story and video_generation."
        )


    # ============================================================
    # SCENE ID VALIDATION
    # ============================================================

    story_ids = [
        scene.get("scene_id")
        for scene in scenes
    ]

    image_ids = [
        scene.get("scene_id")
        for scene in image_scenes
    ]

    video_ids = [
        scene.get("scene_id")
        for scene in video_scenes
    ]


    if story_ids != image_ids:

        raise ValueError(
            "Scene IDs do not match between "
            "user_story and image_generation."
        )


    if story_ids != video_ids:

        raise ValueError(
            "Scene IDs do not match between "
            "user_story and video_generation."
        )


    # ============================================================
    # TIMING + DURATION VALIDATION
    # ============================================================

    total_duration = 0.0

    previous_end = 0.0


    for index, scene in enumerate(
        scenes
    ):

        if not isinstance(
            scene,
            dict
        ):

            raise ValueError(
                f"Scene {index + 1} "
                f"is not a JSON object."
            )


        scene_number = index + 1


        # --------------------------------------------------------
        # Required fields
        # --------------------------------------------------------

        required_fields = [
            "scene_id",
            "start_time",
            "end_time",
            "duration_seconds"
        ]


        for field in required_fields:

            if field not in scene:

                raise ValueError(
                    f"Scene {scene_number} "
                    f"is missing '{field}'. "
                    f"Received keys: "
                    f"{list(scene.keys())}"
                )


        # --------------------------------------------------------
        # Convert timing values
        # --------------------------------------------------------

        try:

            start_time = float(
                scene["start_time"]
            )

            end_time = float(
                scene["end_time"]
            )

            scene_duration = float(
                scene["duration_seconds"]
            )

        except (
            TypeError,
            ValueError
        ):

            raise ValueError(
                f"Scene {scene_number} "
                f"contains invalid timing values."
            )


        # --------------------------------------------------------
        # Validate duration
        # --------------------------------------------------------

        if scene_duration <= 0:

            raise ValueError(
                f"Scene {scene_number} "
                f"has invalid duration: "
                f"{scene_duration}"
            )


        # --------------------------------------------------------
        # Validate start/end calculation
        # --------------------------------------------------------

        calculated_duration = (
            end_time - start_time
        )


        if abs(
            calculated_duration
            - scene_duration
        ) > 0.01:

            raise ValueError(
                f"Scene {scene_number} timing mismatch. "
                f"start={start_time}, "
                f"end={end_time}, "
                f"duration={scene_duration}"
            )


        # --------------------------------------------------------
        # Validate continuity
        # --------------------------------------------------------

        if index == 0:

            if abs(start_time) > 0.01:

                raise ValueError(
                    "First scene must start at 0 seconds."
                )

        else:

            if abs(
                start_time - previous_end
            ) > 0.01:

                raise ValueError(
                    f"Scene {scene_number} "
                    f"does not start where the "
                    f"previous scene ended."
                )


        previous_end = end_time

        total_duration += scene_duration


    # ============================================================
    # FINAL DURATION
    # ============================================================

    print(
        f"Requested duration: {duration}s"
    )

    print(
        f"Generated duration: "
        f"{total_duration}s"
    )


    # ============================================================
    # EXACT DURATION CHECK
    # ============================================================

    if abs(
        total_duration - float(duration)
    ) > 0.01:

        raise ValueError(
            f"Duration mismatch. "
            f"Expected {duration}s, "
            f"got {total_duration}s."
        )


    # ============================================================
    # FINAL END TIME CHECK
    # ============================================================

    if abs(
        previous_end - float(duration)
    ) > 0.01:

        raise ValueError(
            f"Final scene must end at "
            f"{duration}s, "
            f"but ends at {previous_end}s."
        )


    # ============================================================
    # VALIDATION SUCCESS
    # ============================================================

    print(
        "Story validation: PASSED"
    )

    print(
        f"Scenes: {len(scenes)}"
    )

    print(
        f"Duration: {total_duration}s"
    )

    return True