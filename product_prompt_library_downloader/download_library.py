import argparse, json, re, shutil, tempfile, urllib.request, zipfile
from pathlib import Path

REPO = "https://github.com/JeremyGDM/awesome-ai-product-photography-prompts"
ZIP_URL = REPO + "/archive/refs/heads/master.zip"

PROMPT_FILES = {
    "product-photography.md": "product_brand",
    "food-and-drink.md": "food_drink",
    "poster-design.md": "poster_campaign",
}

def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "product-prompt-library-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        path.write_bytes(r.read())

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def variables(prompt):
    out, seen = [], set()
    for x in re.findall(r"\[([^\[\]]+)\]", prompt):
        x = x.strip()
        if x and x.lower() not in seen:
            out.append(x); seen.add(x.lower())
    return out

def heading_before(text, pos):
    hs = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", text[:pos]))
    return hs[-1].group(1).strip() if hs else None

def extract_prompts(text, category, filename):
    pattern = re.compile(r"(?ms)^```(?:[^\n]*)\n(.*?)^```[ \t]*$")
    records = []
    for i, m in enumerate(pattern.finditer(text), 1):
        prompt = m.group(1).replace("\r\n","\n").replace("\r","\n").strip()
        if not prompt:
            continue
        name = heading_before(text, m.start()) or f"{category.replace('_',' ').title()} Prompt {i}"
        records.append({
            "id": f"{category}-{i:03d}",
            "name": name,
            "category": "product_ads",
            "subcategory": category,
            "prompt": prompt,
            "variables": variables(prompt),
            "image": None,
            "source": REPO,
            "source_file": f"prompts/{filename}"
        })
    return records

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="./product-prompt-library")
    args = ap.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zipfile_path = td / "repo.zip"
        print("Downloading repository...")
        download(ZIP_URL, zipfile_path)

        extract_dir = td / "extract"
        with zipfile.ZipFile(zipfile_path) as z:
            z.extractall(extract_dir)
        root = next(p for p in extract_dir.iterdir() if p.is_dir())

        src_prompts = output / "source-prompts"
        if src_prompts.exists(): shutil.rmtree(src_prompts)
        src_prompts.mkdir(parents=True)

        templates = []
        for filename, category in PROMPT_FILES.items():
            src = root / "prompts" / filename
            if not src.exists():
                print("WARNING: missing", src)
                continue
            text = src.read_text(encoding="utf-8", errors="replace")
            shutil.copy2(src, src_prompts / filename)
            rows = extract_prompts(text, category, filename)
            templates.extend(rows)
            print(f"{filename}: {len(rows)} prompt blocks")

        images_src = root / "images"
        images_dst = output / "images"
        if images_dst.exists(): shutil.rmtree(images_dst)
        image_count = 0
        if images_src.exists():
            shutil.copytree(images_src, images_dst)
            image_count = sum(1 for p in images_dst.rglob("*") if p.is_file())

        (output / "templates.json").write_text(
            json.dumps({
                "version": 1,
                "source": REPO,
                "category": {"id": "product_ads", "name": "Product Ads"},
                "templates": templates
            }, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        license_src = root / "LICENSE"
        if license_src.exists():
            shutil.copy2(license_src, output / "SOURCE_LICENSE.txt")

        (output / "source-manifest.json").write_text(
            json.dumps({
                "source": REPO,
                "download_url": ZIP_URL,
                "branch": "master",
                "license_note": "The repository README currently states CC0 1.0."
            }, indent=2),
            encoding="utf-8"
        )

        print("\nDONE")
        print("Templates:", len(templates))
        print("Repository image files:", image_count)
        print("Output:", output)

if __name__ == "__main__":
    main()
