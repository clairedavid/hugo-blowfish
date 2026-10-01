#!/usr/bin/env python3
"""Turn the research content source into data/research.json.

Source layout (default --src ~/Desktop/website_meta/research/machine-learning):
    _intro.txt            one-line intro for the "Machine Learning" theme
    <slug>/_content.txt   one project, in == SECTION == blocks

Each project's _content.txt holds, in this order:
    == CARD ==          Key: value lines (Title, Subtitle, Years, Status,
                         Card image)
    == BANNER ==         Images: (one filename stem per line) / Style:
    == LEFT PANEL ==     Role: / Years: / Status: (optional, see below) /
                         Team: (pipe rows "image | name | affiliation") /
                         Links: (pipe rows "label | url", or "(none)")
    == PAGE HEADING ==   a single line, becomes the page's title and h1
    == TEXT ==           markdown: paragraphs, *emphasis*, a quote as two
                         `> ` lines (text, then attribution)
    == FIGURES ==        optional, image stems one per line, or "(none...)"
    == TECHNICAL ==      markdown, folded into a <details> on the page

TEXT and TECHNICAL are stored as raw markdown and rendered at template time
with Hugo's own `markdownify`, rather than reimplemented here: the source is
already close to markdown (it uses *emphasis* and > quotes natively), so
re-parsing it in Python would just be a worse copy of Goldmark. $...$ maths is
left untouched in that markdown; it survives Goldmark unharmed because every
expression in this content has its underscores flanked by letters or digits,
which CommonMark's intraword-emphasis rule already protects, and KaTeX's own
auto-render (loaded by the page when `has_math` is true) renders it
client-side afterwards.

Images are referenced here by filename stem only (no extension). The site
build copies whichever finals actually exist for that stem from
_converted/ into assets/research/<slug>/, so this script does not need to
know which format(s) a given stem ships in; see copy_assets().

Usage:  python3 scripts/build-research-data.py [--src PATH]
"""
import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SRC = pathlib.Path.home() / "Desktop/website_meta/research/machine-learning"
OUT = ROOT / "data" / "research.json"
ASSETS_OUT = ROOT / "assets" / "research"
CONTENT_OUT = ROOT / "content" / "research"

# Phase-1 review artifacts that live alongside the real finals in
# _converted/ but are never site assets.
NOT_ASSETS = {"preview.html", "maths-sample.png", "raktim_circle_preview.png"}

EMPTY_MARKERS = re.compile(r"^\(none\b", re.I)


def parse_sections(text):
    """Split a _content.txt on == NAME == markers into {NAME: body}."""
    parts = re.split(r"^==\s*([A-Z ]+?)\s*==\s*$", text, flags=re.M)
    # parts[0] is anything before the first marker (should be empty)
    out = {}
    for i in range(1, len(parts), 2):
        out[parts[i].strip()] = parts[i + 1].strip("\n")
    return out


def parse_kv(body):
    """`Key: value` lines, one per line, into a dict. A key's value may be
    blank, meaning its content is the indented/plain lines that follow (used
    for Team: and Links:, handled separately by the caller)."""
    kv = {}
    for line in body.split("\n"):
        line = line.rstrip()
        if not line or line.startswith(("Team:", "Links:", "Images:")):
            continue
        m = re.match(r"^([A-Za-z ]+):\s*(.*)$", line)
        if m and m.group(1).strip() in (
            "Title", "Subtitle", "Years", "Status", "Card image",
            "Style", "Role",
        ):
            kv[m.group(1).strip()] = m.group(2).strip()
    return kv


def stem(name):
    return pathlib.Path(name.strip()).stem


def parse_pipe_rows(body, after_label):
    """Lines of `a | b | c` following a `<after_label>:` marker, up to the
    next blank-prefixed label or end of body. Returns [] for "(none)"."""
    lines = body.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith(after_label + ":"))
    except StopIteration:
        return []
    first = lines[start].split(":", 1)[1].strip()
    rows = [first] if first else []
    for l in lines[start + 1:]:
        if re.match(r"^[A-Za-z ]+:\s*", l) and "|" not in l:
            break
        if l.strip():
            rows.append(l.strip())
    rows = [r for r in rows if r]
    if len(rows) == 1 and EMPTY_MARKERS.match(rows[0]):
        return []
    return [tuple(p.strip() for p in r.split("|")) for r in rows]


def parse_image_list(body):
    lines = [l.strip() for l in body.split("\n")]
    try:
        start = lines.index("Images:")
    except ValueError:
        return []
    out = []
    for l in lines[start + 1:]:
        if not l:
            continue
        if l.startswith("Style:"):
            break
        out.append(stem(l))
    return out


# The CARD section's "Card image:" line is prose describing what was done
# ("xy_uphi_fd_pinn_dphi010_demo.pdf, left plot only, cropped with equal
# margins around the axes"), not necessarily the final asset's own filename.
# PINN's card is a distinct cropped derivative, pinn-card, that the prose
# names only indirectly; this is the one case here where the described source
# and the actual asset stem differ, so it is resolved explicitly rather than
# guessed at from the sentence.
CARD_IMAGE_OVERRIDE = {
    "pinn": "pinn-card",
}


def parse_card(body, slug):
    kv = parse_kv(body)
    card_image_desc = kv.get("Card image", "")
    image_stem = CARD_IMAGE_OVERRIDE.get(slug) or (
        stem(card_image_desc.split(",")[0]) if card_image_desc else "")
    fit = "contain" if re.search(r"\bwhole\b", card_image_desc, re.I) else "cover"
    return {
        "title": kv.get("Title", ""),
        "subtitle": kv.get("Subtitle", ""),
        "years": kv.get("Years", ""),
        "status": kv.get("Status", ""),
        "image": image_stem,
        "fit": fit,
    }


def parse_banner(body):
    kv = parse_kv(body)
    return {
        "images": parse_image_list(body),
        "style": kv.get("Style", "row"),
    }


def parse_panel(body, card):
    kv = parse_kv(body)
    team = [
        {"image": stem(r[0]), "name": r[1], "affiliation": r[2] if len(r) > 2 else ""}
        for r in parse_pipe_rows(body, "Team")
    ]
    links = [
        {"label": r[0], "url": r[1] if len(r) > 1 else ""}
        for r in parse_pipe_rows(body, "Links")
    ]
    return {
        "role": kv.get("Role", ""),
        # Years/Status fall back to the CARD's own, when the panel does not
        # give its own: GAE narrows Years to its actual supervision window
        # and relies on CARD for Status; PINN repeats neither and relies on
        # CARD for both. Ambiguity resolved this way, see the script's
        # module docstring and the build report.
        "years": kv.get("Years") or card["years"],
        "status": kv.get("Status") or card["status"],
        "team": team,
        "links": links,
    }


def parse_figures(body):
    if body is None:
        return []
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if not lines or EMPTY_MARKERS.match(lines[0]):
        return []
    return [stem(l) for l in lines]


QUOTE_ATTRIB_RE = re.compile(r'(^> ".*"\s*)\n(> [^\n]+)$', re.M)


def split_quote_attribution(md):
    """`> "quote"` directly followed by `> Name` (no blank line between them)
    is, in CommonMark, one blockquote with the two lines folded into a single
    paragraph by the soft-line-break rule, so the attribution runs straight
    into the quote's own last sentence. A blank `>` line between them keeps
    both inside the same blockquote but as two separate <p> elements, which
    .res can then style as a distinct attribution line, with no em dash and
    no raw HTML needed in the source."""
    return QUOTE_ATTRIB_RE.sub(r"\1\n>\n\2", md)


def has_math(*texts):
    return any("$" in (t or "") for t in texts)


def build_project(slug, path):
    sections = parse_sections(path.read_text(encoding="utf-8"))
    required = ["CARD", "BANNER", "LEFT PANEL", "PAGE HEADING", "TEXT", "TECHNICAL"]
    missing = [s for s in required if s not in sections]
    if missing:
        print(f"  ERROR {slug}: missing sections {missing}", file=sys.stderr)
        sys.exit(1)

    card = parse_card(sections["CARD"], slug)
    banner = parse_banner(sections["BANNER"])
    panel = parse_panel(sections["LEFT PANEL"], card)
    text = split_quote_attribution(sections["TEXT"].strip())
    technical = sections["TECHNICAL"].strip()
    figures = parse_figures(sections.get("FIGURES"))

    return {
        "slug": slug,
        "card": card,
        "banner": banner,
        "panel": panel,
        "page_heading": sections["PAGE HEADING"].strip(),
        "text": text,
        "figures": figures,
        "technical": technical,
        "has_math": has_math(text, technical),
    }


def collect_assets(*projects):
    """stem -> True for every image stem referenced by these projects."""
    stems = set()
    for p in projects:
        stems.add(p["card"]["image"])
        stems.update(p["banner"]["images"])
        stems.update(p["figures"])
        stems.update(m["image"] for m in p["panel"]["team"])
    stems.discard("")
    return stems


def copy_assets(src_converted, projects):
    """Copy every file in _converted/ whose stem is referenced, into
    assets/research/<slug>/, matching by stem and ignoring extension so the
    .jpg portrait, the .svg plots etc. are picked up regardless of what
    extension the content file's prose happens to mention. A stem with
    several files (e.g. pinn-card.png + .png.webp) copies all of them."""
    available = [f for f in src_converted.iterdir()
                 if f.is_file() and f.name not in NOT_ASSETS]
    by_stem = {}
    for f in available:
        by_stem.setdefault(f.stem, []).append(f)

    report = []
    for p in projects:
        needed = collect_assets(p)
        dest_dir = ASSETS_OUT / p["slug"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        for s in sorted(needed):
            files = by_stem.get(s)
            if not files:
                report.append((p["slug"], s, "MISSING"))
                continue
            for f in files:
                shutil.copy2(f, dest_dir / f.name)
            report.append((p["slug"], s, ", ".join(f.name for f in files)))
    return report


def write_content_pages(projects):
    """content/research/<slug>/_index.md for each project: front matter with
    the page_heading as title (Hugo's simple.html renders that as the h1, so
    this alone satisfies "H1 is the PAGE HEADING field"), the katex marker
    shortcode only when has_math is true, and the research-page call.
    Rewritten every run, same as data/research.json: nothing hand-authored
    belongs in these files, so there is nothing to lose by overwriting them.
    content/research/_index.md (the overview) is NOT written here: unlike
    these, it carries no data-derived front matter and so is authored once,
    by hand, alongside the menu and alias changes."""
    for p in projects:
        slug = p["slug"]
        dest = CONTENT_OUT / slug
        dest.mkdir(parents=True, exist_ok=True)
        title = json.dumps(p["page_heading"], ensure_ascii=False)
        katex_marker = "{{< katex >}}\n\n" if p["has_math"] else ""
        md = (
            "---\n"
            "layout: \"simple\"\n"
            f"title: {title}\n"
            "---\n\n"
            f"{katex_marker}"
            f"{{{{< research-page slug=\"{slug}\" >}}}}\n"
        )
        (dest / "_index.md").write_text(md, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path, default=DEFAULT_SRC)
    args = ap.parse_args()

    intro_path = args.src / "_intro.txt"
    intro = intro_path.read_text(encoding="utf-8").strip() if intro_path.exists() else ""

    projects = []
    for slug in ("pinn", "gae"):
        content = args.src / slug / "_content.txt"
        if not content.exists():
            print(f"ERROR: {content} not found", file=sys.stderr)
            sys.exit(1)
        projects.append(build_project(slug, content))

    data = {
        "themes": [
            {
                "id": "machine-learning",
                "title": "Machine Learning",
                "intro": intro,
                "projects": projects,
            }
        ]
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_content_pages(projects)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(projects)} project(s)")
    for p in projects:
        print(f"  {p['slug']:6} math={p['has_math']!s:5}  "
              f"team={len(p['panel']['team'])}  links={len(p['panel']['links'])}  "
              f"banner={len(p['banner']['images'])}  figures={len(p['figures'])}")

    converted = args.src / "_converted"
    if converted.is_dir():
        print(f"\ncopying assets from {converted}")
        for slug, s, result in copy_assets(converted, projects):
            print(f"  {slug:6} {s:32} -> {result}")
    else:
        print(f"\nWARNING: {converted} not found, no assets copied", file=sys.stderr)


if __name__ == "__main__":
    main()
