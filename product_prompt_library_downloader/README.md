# Product Prompt Library Downloader

Downloads the JeremyGDM product photography prompt repository and converts its Markdown prompt blocks into `templates.json`.

Source:
https://github.com/JeremyGDM/awesome-ai-product-photography-prompts

## Run

```bash
python download_library.py
```

Optional:

```bash
python download_library.py --output ./product-prompt-library
```

## Output

```text
product-prompt-library/
├── images/
├── source-prompts/
├── templates.json
├── source-manifest.json
└── SOURCE_LICENSE.txt
```

The parser extracts bracketed placeholders such as `[PRODUCT]` into the `variables` array.

The script copies only images actually present in the GitHub repository. It does not scrape the external Pixonara gallery.

The upstream README currently states CC0 1.0. Keep the license file and verify the upstream license before redistributing assets.
