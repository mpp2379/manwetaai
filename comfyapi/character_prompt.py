# ============================================================
# Character image prompt builder
#
# Takes structured user inputs and assembles them into a
# detailed character portrait prompt for Flux 1 Schnell,
# following the same structure as the reference prompt.
# ============================================================


def _clean(value):

    if value is None:
        return ""

    return str(value).strip()


def build_character_prompt(

    gender="",
    age="",
    ethnicity="",

    face_shape="",
    eye_color="",
    eye_shape="",
    face_details="",
    distinctive_marks="",

    hair="",
    body="",
    clothing="",
    expression="",
    visual_style="",
    extra_details=""
):
    """
    Build a full character portrait generation prompt
    from structured form inputs.
    """

    # --------------------------------------------------------
    # Subject line
    # --------------------------------------------------------

    subject_parts = []

    age_text = _clean(age)

    if age_text:

        try:
            age_text = f"{int(float(age_text))}-year-old"
        except ValueError:
            pass

    for part in (age_text, _clean(ethnicity), _clean(gender)):

        if part:
            subject_parts.append(part)

    if not subject_parts:
        subject = "a person"
    else:
        subject = " ".join(subject_parts)

    lines = []

    lines.append(
        "Create a highly detailed, photorealistic full-body "
        f"character reference sheet of a **{subject}** with a "
        "distinctive, memorable appearance and strong visual identity."
    )

    # --------------------------------------------------------
    # Character sheet layout
    # --------------------------------------------------------

    lines.append(
        "**Character sheet layout:** multiple views of the exact "
        "same character arranged side by side on a plain neutral "
        "background — front view standing pose facing the camera, "
        "side profile view, and back view, plus an additional "
        "close-up head shot of the face from the front and top "
        "angle showing the hairstyle and hairline clearly. All "
        "views must show identical facial features, proportions, "
        "outfit and colors, like a professional animation or game "
        "production model sheet."
    )

    # --------------------------------------------------------
    # Face
    # --------------------------------------------------------

    face_parts = [
        p for p in (
            _clean(face_shape),
            _clean(eye_color),
            _clean(face_details)
        )
        if p
    ]

    marks = _clean(distinctive_marks)

    if marks:
        face_parts.append(marks)

    if face_parts:
        lines.append(
            "**Face:** " + ", ".join(face_parts) + ". "
            "Natural skin texture with realistic pores "
            "and fine facial details."
        )

    # --------------------------------------------------------
    # Hair
    # --------------------------------------------------------

    hair_text = _clean(hair)

    if hair_text:
        lines.append(
            f"**Hair:** {hair_text}."
        )

    # --------------------------------------------------------
    # Body
    # --------------------------------------------------------

    body_text = _clean(body)

    lines.append(
        "**Body:** realistic human proportions, "
        + (
            f"{body_text}, "
            if body_text
            else ""
        )
        + "anatomically accurate hands and facial structure."
    )

    # --------------------------------------------------------
    # Clothing
    # --------------------------------------------------------

    clothing_text = _clean(clothing)

    if clothing_text:
        lines.append(
            f"**Clothing:** {clothing_text}, no visible logos."
        )

    # --------------------------------------------------------
    # Expression
    # --------------------------------------------------------

    expression_text = _clean(expression)

    if expression_text:
        lines.append(
            f"**Expression:** {expression_text}."
        )

    # --------------------------------------------------------
    # Extra details
    # --------------------------------------------------------

    extra_text = _clean(extra_details)

    if extra_text:
        lines.append(
            f"**Additional details:** {extra_text}."
        )

    # --------------------------------------------------------
    # Visual style
    # --------------------------------------------------------

    style_text = _clean(visual_style)

    if not style_text:
        style_text = (
            "ultra-realistic photography, even soft studio lighting "
            "across all views, flat neutral light-gray background, "
            "natural skin tones, realistic eyes, detailed hair strands, "
            "physically accurate shadows, full-body framing with "
            "consistent scale between views, professional animation "
            "production model sheet, crisp details, realistic texture"
        )

    lines.append(
        f"**Visual style:** {style_text}."
    )

    # --------------------------------------------------------
    # Character consistency block
    # --------------------------------------------------------

    lines.append(
        "**Character consistency requirements:** maintain the "
        "exact same facial identity, facial proportions, skin "
        "tone, hairstyle, eye color, body proportions and "
        "overall appearance whenever this character is "
        "generated again. Avoid exaggerated beauty filters, "
        "plastic skin, facial distortion, asymmetrical eyes, "
        "extra fingers, deformed hands, or unrealistic anatomy."
    )

    lines.append(
        "Clean composition, highly detailed, photorealistic, "
        "natural and believable human appearance."
    )

    return "\n\n".join(lines)