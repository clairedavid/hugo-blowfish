#!/usr/bin/env python3
"""Turn the research content source into data/research.json.

Source layout (default --src ~/Desktop/website_meta/research):
    <theme>/_intro.txt            one-line intro for that theme
    <theme>/<slug>/_content.txt   one project, in == SECTION == blocks

Themes are fixed, in site order: "machine-learning" (Machine Learning),
"dune" (DUNE), then "atlas" (ATLAS). Machine Learning's two projects and
ATLAS's one keep their own fixed order; DUNE's projects are discovered from
its subdirectories and sorted by an optional "Order:" line in == CARD ==
(lower first), falling back to alphabetical name for folders that do not set
one, so dune-canada sorts before dune-computing without needing one.

Each project's _content.txt holds, in this order:
    == CARD ==          Key: value lines (Title, Subtitle, Years, Status,
                         Card image, optional Order, optional "Unlisted:
                         yes": the page still builds at its URL but is left
                         out of the overview grid, so Subtitle/Years/Card
                         image may then be empty or absent)
    == BANNER ==         Either "Image:" (one pre-composed banner, optional
                         "Credit:" line) or the older "Images:" list (one
                         filename stem per line) / "Style:"
    == LEFT PANEL ==     Role: / Years: / Status: (optional, see below) /
                         optional Logo: (one image, shown above Links) /
                         Team: (pipe rows "image | name | affiliation",
                         affiliation may itself be "role · affiliation") /
                         optional Facts: (see parse_facts_lines: a
                         "<Label>:" line on its own starts an entry, the
                         "::center <value>" lines under it are that entry's
                         values, a blank line ends it; rendered first in the
                         panel) / Links: (pipe rows "label | url", inline
                         markdown [text](url), a markdown image
                         "![alt](file)", or "(none)"; the first content line
                         may be "Label: <text>" to override the panel's
                         "Links" heading; an image line's file may have a
                         "<stem>-dark" sibling of any extension in
                         _converted/, shown instead in dark mode)
    == PAGE HEADING ==   a single line, becomes the page's title and h1
    == TEXT ==           markdown: paragraphs, *emphasis*, a quote as two
                         `> ` lines (text, then attribution), and optionally
                         one or more [[FIGURE-ROW]]...[[/FIGURE-ROW]] blocks
                         (see parse_figure_row_block). A single-image row
                         fills the column's full width; any image whose
                         corners are all light and opaque (see
                         image_needs_frame) is framed in the same white
                         figure card used elsewhere, photos are not.
                         A markdown link starting with "/" is internal:
                         resolved via site.GetPage, same tab, no
                         target=_blank (see partials/research/link.html);
                         this applies here, in the theme intro and in the
                         panel's Links block alike.
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
client-side afterwards. Inline [text](url) links (Links:, the theme intro)
are the one exception handled in Python instead: markdownify alone cannot add
target="_blank"/rel="noopener" to just those links without a site-wide render
hook, so they are split into plain-text/link segments here and the template
renders each segment itself.

Images are referenced here by filename stem only (no extension). The site
build copies whichever finals actually exist for that stem from a theme's
own _converted/ into assets/research/<slug>/, so this script does not need
to know which format(s) a given stem ships in; see copy_assets(). A
"<file> <-- comment" trailing note after a filename field (Card image:,
Image:, Logo:) is a human note-to-self in the source and is stripped before
the filename is read.

Usage:  python3 scripts/build-research-data.py [--src PATH]
"""
import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SRC = pathlib.Path.home() / "Desktop/website_meta/research"
OUT = ROOT / "data" / "research.json"
ASSETS_OUT = ROOT / "assets" / "research"
CONTENT_OUT = ROOT / "content" / "research"

THEME_DEFS = [
    {"id": "machine-learning", "title": "Machine Learning", "folder": "machine-learning", "slugs": ("pinn", "gae")},
    {"id": "dune", "title": "DUNE", "folder": "dune", "slugs": None},
    {"id": "atlas", "title": "ATLAS", "folder": "atlas", "slugs": ("atlas-experiment", "atlas-tthbb", "atlas-itk", "atlas-susy", "diamond")},
    {"id": "icecube", "title": "IceCube", "folder": "icecube", "slugs": ("desy-zeuthen",)},
]

# Phase-1 review artifacts that live alongside the real finals in
# _converted/ but are never site assets.
NOT_ASSETS = {"preview.html", "maths-sample.png", "raktim_circle_preview.png"}

EMPTY_MARKERS = re.compile(r"^\(none\b", re.I)
TRAILING_COMMENT_RE = re.compile(r"\s*<--.*$")
ORIGINAL_SOURCE_RE = re.compile(r"<--\s*from\s+(\S+)")


def original_source_stem(raw_value):
    """A "<-- from original.jpg, ..." comment names the one photo a target
    file (a banner, a card thumbnail) was made from. Two targets with
    different final names, e.g. dune-computing-banner.jpg and
    dune-computing-card.jpg, can both carry this comment pointing at the
    same original, which is how resolve_card_credit finds a card's credit
    when the card and banner do not share a filename at all."""
    m = ORIGINAL_SOURCE_RE.search(raw_value)
    return stem(m.group(1)) if m else ""


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
            "Title", "Subtitle", "Years", "Status", "Card image", "Order",
            "Style", "Role", "Image", "Credit", "Logo", "Unlisted",
        ):
            kv[m.group(1).strip()] = m.group(2).strip()
    return kv


def stem(name):
    return pathlib.Path(TRAILING_COMMENT_RE.sub("", name).strip()).stem


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


def parse_card(body, slug, converted_dir):
    """The CARD section's "Card image:" line is prose describing what was
    done, or sometimes the final asset's own filename directly (DUNE); not
    necessarily the stem the page should actually use, since a file named
    <slug>-card.* in _converted/, if one exists, overrides it outright: that
    naming convention means "this is the purpose-built thumbnail for this
    card," always taking priority over whatever the prose happens to say.
    source_stem is kept separately (the literal, un-overridden reference)
    so build_project can cross-reference it against the banner's and any
    figure-row image's own credit, for item 5's "same photo, same credit on
    the card" rule, without the override renaming getting in the way."""
    kv = parse_kv(body)
    card_image_desc = kv.get("Card image", "")
    # Comment stripped before the comma-split: an ML-style "file.pdf, left
    # plot only..." description clause and a DUNE-style "file.jpg <-- from
    # original.jpg, 2000px wide..." note both use a comma, for two different
    # reasons, and only the first comma (if any) after the real filename
    # should end up splitting anything.
    clean_desc = TRAILING_COMMENT_RE.sub("", card_image_desc).strip()
    source_stem = stem(clean_desc.split(",")[0]) if clean_desc else ""
    override = f"{slug}-card"
    has_override = converted_dir and any(
        (converted_dir / f"{override}{ext}").exists()
        for ext in (".png", ".webp", ".jpg", ".svg"))
    image_stem = override if has_override else source_stem
    return {
        "title": kv.get("Title", ""),
        "subtitle": kv.get("Subtitle", ""),
        "years": kv.get("Years", ""),
        "status": kv.get("Status", ""),
        "image": image_stem,
        "source_stem": source_stem,
        "original_stem": original_source_stem(card_image_desc),
        "credit": "",  # filled in by build_project once the banner/figure-row credits are known
        # "Unlisted: yes" builds the page at its URL but leaves it out of the
        # overview grid (research-overview.html skips it); Subtitle/Years/
        # Card image may then be empty, which is fine since nothing reads
        # them for a page that is never shown as a tile.
        "unlisted": kv.get("Unlisted", "").strip().lower() in ("yes", "true"),
    }


def parse_banner(body, slug, converted_dir):
    """Three ways a banner can be specified, checked in this order:
    1. An explicit "Image:" line (one pre-composed banner), with an
       optional "Credit:" line shown centred under it on the page.
    2. A file named <slug>-banner.* in _converted/, the same override
       convention as parse_card's <slug>-card, for a banner that is not
       named directly in the prose.
    3. The older "Images:" list rendered as a same-height row, for any
       project that has not been moved to a single pre-composed banner."""
    kv = parse_kv(body)
    credit = kv.get("Credit", "")
    explicit_image = kv.get("Image", "")
    if explicit_image:
        return {"images": [], "style": "single", "single": stem(explicit_image),
                "original_stem": original_source_stem(explicit_image), "credit": credit}
    override = f"{slug}-banner"
    has_override = converted_dir and any(
        (converted_dir / f"{override}{ext}").exists()
        for ext in (".png", ".webp", ".jpg", ".svg"))
    if has_override:
        return {"images": [], "style": "single", "single": override, "original_stem": "", "credit": credit}
    return {
        "images": parse_image_list(body),
        "style": kv.get("Style", "row"),
        "single": "",
        "original_stem": "",
        "credit": credit,
    }


# The url may hold one level of balanced parentheses, e.g. doi.org/10.1007/JHEP10(2015)134
INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(((?:[^()]|\([^()]*\))+)\)")
IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
LINKED_IMAGE_RE = re.compile(r"^\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)$")


def parse_inline_segments(text):
    """Split prose containing zero or more [text](url) links into alternating
    plain-text/link segments: {"text", "url": ""} for plain runs, {"text",
    "url"} for a link. Used for both a Links: line and the theme intro, so
    the template can render each with explicit target="_blank" rel="noopener"
    on just the link segments, something plain markdownify cannot do without
    a site-wide render hook."""
    segments = []
    pos = 0
    for m in INLINE_LINK_RE.finditer(text):
        if m.start() > pos:
            segments.append({"text": text[pos:m.start()], "url": ""})
        segments.append({"text": m.group(1), "url": m.group(2)})
        pos = m.end()
    if pos < len(text):
        segments.append({"text": text[pos:], "url": ""})
    if not segments:
        segments.append({"text": text, "url": ""})
    return segments


CENTER_PREFIX_RE = re.compile(r"^::center\s+")
LABEL_OVERRIDE_RE = re.compile(r"^Label:\s*(.+)$")


def asset_exists(converted_dir, stem_name):
    return bool(converted_dir) and any(
        (converted_dir / f"{stem_name}{ext}").exists()
        for ext in (".png", ".webp", ".jpg", ".svg"))


def parse_links_lines(body, slug, converted_dir):
    """Lines after "Links:", in one of three forms: the old "label | url"
    row (parse_pipe_rows' own format); prose containing one or more inline
    [text](url) links, where only the bracketed text is ever clickable and
    the url itself is never shown; or a standalone markdown image
    "![alt](file)", rendered full panel width instead of as a link. Which
    form a line is in is decided by its own syntax, not by the presence of a
    pipe, since neither of the other two forms has one. A line may start
    with "::center " (stripped before the rest is parsed) to render that one
    item centred instead of the panel's own default left/ragged-right; an
    image is always centred regardless, since there is no reading where a
    panel logo would sit left-aligned. An "image" entry whose file does not
    actually exist in converted_dir is dropped (not an errorf at render
    time): that is the one place in this panel a missing asset is expected
    and should not break the build, matching parse_card/parse_banner's own
    override-checks rather than research/picture.html's normal hard-fail.
    A bare image may itself be the link: "[![alt](file)](url)" (a linked
    image) carries that url as "href" instead of being wrapped in a
    separate inline link item, for a logo that is its own call to action
    with no extra "visit" text needed. An image entry also looks for a
    "<src>-dark" sibling in converted_dir (any extension, independent of the
    light image's own) and records it as "dark_src": the template renders
    both and toggles which one shows with the .dark ancestor class, the same
    light/dark swap convention used for every other themed asset on this
    site, so a logo whose official dark version only exists as e.g. an SVG
    next to a PNG still works.
    The first content line may be "Label: <text>" (e.g. "Label: Official
    website"), which overrides the panel's own "Links" field heading instead
    of being parsed as a link. Consecutive non-blank lines form one group
    (a label with the link or logo under it); a blank line starts a new one.
    Returns ("Links" or override, groups), groups being a list of groups,
    each a list of {"kind": "plain", "label", "url", "centered"}, {"kind":
    "inline", "segments": [...], "centered"} or {"kind": "image", "alt",
    "src", "dark_src", "href", "centered": True}."""
    lines = body.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith("Links:"))
    except StopIteration:
        return "Links", []
    first = lines[start].split(":", 1)[1].strip()
    # Blank lines are kept (as "") because they are the group breaks.
    raw = [first] if first else []
    for l in lines[start + 1:]:
        # A genuine next LEFT PANEL field, not a Links: content line that
        # happens to end in ":" too ("Paper:", "DUNE automated glossary:",
        # "Coffea Python toolkit:" are all labels, not section markers):
        # checked against the actual field names this format has, not any
        # "word(s) then colon" line.
        if re.match(r"^(Role|Years|Status|Logo|Team|Links):\s*", l):
            break
        raw.append(l.strip())
    while raw and not raw[0]:
        raw.pop(0)
    while raw and not raw[-1]:
        raw.pop()
    if len(raw) == 1 and EMPTY_MARKERS.match(raw[0]):
        return "Links", []

    label = "Links"
    overridden = False
    if raw and LABEL_OVERRIDE_RE.match(raw[0]):
        label = LABEL_OVERRIDE_RE.match(raw[0]).group(1).strip()
        overridden = True
        raw = raw[1:]
        while raw and not raw[0]:
            raw.pop(0)

    groups = [[]]
    for line in raw:
        if not line:
            if groups[-1]:
                groups.append([])
            continue
        out = groups[-1]
        centered = bool(CENTER_PREFIX_RE.match(line))
        line = CENTER_PREFIX_RE.sub("", line)
        lm = LINKED_IMAGE_RE.match(line)
        m = lm or IMAGE_LINE_RE.match(line)
        if m:
            src = stem(m.group(2))
            if not asset_exists(converted_dir, src):
                print(f"  WARNING {slug}: Links image {m.group(2)!r} not found in "
                      f"_converted/, skipping", file=sys.stderr)
                continue
            dark_src = f"{src}-dark"
            if not asset_exists(converted_dir, dark_src):
                dark_src = ""
            href = lm.group(3) if lm else ""
            out.append({"kind": "image", "alt": m.group(1), "src": src,
                        "dark_src": dark_src, "href": href, "centered": True})
        elif INLINE_LINK_RE.search(line):
            out.append({"kind": "inline", "segments": parse_inline_segments(line), "centered": centered})
        else:
            parts = [p.strip() for p in line.split("|")]
            out.append({"kind": "plain", "label": parts[0],
                        "url": parts[1] if len(parts) > 1 else "", "centered": centered})
    groups = [g for g in groups if g]
    # The default heading is singular when the block holds exactly one URL
    # (a "Label:" override is always kept as written).
    n_urls = sum(
        (1 if it["kind"] == "plain" and it["url"] else 0)
        + (sum(1 for seg in it["segments"] if seg["url"]) if it["kind"] == "inline" else 0)
        + (1 if it["kind"] == "image" and it["href"] else 0)
        for g in groups for it in g)
    if not overridden and n_urls == 1:
        label = "Link"
    return label, groups


FACT_LABEL_RE = re.compile(r"^([^:]+):\s*$")


def parse_facts_lines(body):
    """Lines after "Facts:", up to the next LEFT PANEL field or end of body.
    A line that is only "<Label>:" (nothing after the colon) starts an
    entry; "::center <value>" lines that follow are that entry's values, one
    per line, trailing spaces trimmed; a blank line ends the entry (the next
    label line would end it anyway, this just also covers a stray blank
    inside one). Returns a list of {"label", "values": [...]}, in source
    order, rendered first in the panel (see research-page.html), each as its
    own block in the panel's normal field spacing, label styled like Role/
    Years/Status, values centred under it."""
    lines = body.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "Facts:")
    except StopIteration:
        return []
    entries = []
    cur = None
    for l in lines[start + 1:]:
        if re.match(r"^(Role|Years|Status|Logo|Team|Links):\s*", l):
            break
        stripped = l.strip()
        if not stripped:
            if cur:
                entries.append(cur)
                cur = None
            continue
        if stripped.startswith("::center"):
            if cur is not None:
                cur["values"].append(CENTER_PREFIX_RE.sub("", stripped).strip())
            continue
        m = FACT_LABEL_RE.match(stripped)
        if m:
            if cur:
                entries.append(cur)
            cur = {"label": m.group(1).strip(), "values": []}
    if cur:
        entries.append(cur)
    return entries


def parse_panel(body, card, slug, converted_dir):
    kv = parse_kv(body)
    team = [
        {"image": stem(r[0]), "name": r[1],
         "lines": [p.strip() for p in r[2].split(" · ")] if len(r) > 2 and r[2].strip() else []}
        for r in parse_pipe_rows(body, "Team")
    ]
    facts = parse_facts_lines(body)
    links_label, links = parse_links_lines(body, slug, converted_dir)
    return {
        "role": kv.get("Role", ""),
        # Years/Status fall back to the CARD's own, when the panel does not
        # give its own: GAE narrows Years to its actual supervision window
        # and relies on CARD for Status; PINN repeats neither and relies on
        # CARD for both. Ambiguity resolved this way, see the script's
        # module docstring and the build report.
        "years": kv.get("Years") or card["years"],
        "status": kv.get("Status") or card["status"],
        "logo": stem(kv["Logo"]) if kv.get("Logo") else "",
        "team": team,
        "facts": facts,
        "links_label": links_label,
        "links": links,
    }


def parse_figures(body):
    if body is None:
        return []
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if not lines or EMPTY_MARKERS.match(lines[0]):
        return []
    return [stem(l) for l in lines]


FIGURE_ROW_RE = re.compile(r"\[\[FIGURE-ROW\]\](.*?)\[\[/FIGURE-ROW\]\]", re.S)


def parse_figure_row_block(body):
    """The body between [[FIGURE-ROW]] markers: repeating Image:/Caption:/
    Credit: triples (plus an optional Width: <n>%), one figure per Image:
    line. Caption is kept as raw
    markdown (rendered with markdownify at template time, like TEXT itself);
    width/height/ratio are filled in later, once the final copied asset
    exists to measure (see attach_figure_row_sizes)."""
    images = []
    cur = None
    for line in body.strip("\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Image:"):
            if cur:
                images.append(cur)
            cur = {"image": stem(line.split(":", 1)[1]), "caption": "", "credit": ""}
        elif line.startswith("Caption:") and cur is not None:
            cur["caption"] = line.split(":", 1)[1].strip()
        elif line.startswith("Credit:") and cur is not None:
            cur["credit"] = line.split(":", 1)[1].strip()
        elif line.startswith("Width:") and cur is not None:
            # optional, for a single-image row: the image's share of the text
            # column in percent (see partials/research/figure-row.html)
            cur["width_pct"] = float(line.split(":", 1)[1].strip().rstrip("%"))
    if cur:
        images.append(cur)
    return images


def apply_hard_wraps(md):
    """A single newline inside an ordinary paragraph becomes a real line
    break instead of Goldmark's default CommonMark soft wrap (rendered as
    just a space): two trailing spaces before the newline is CommonMark's
    own hard-break syntax, so this needs no site-wide markup.toml change
    (hardWraps would do the same thing, but for every page on the site, not
    just this one field). A blank line still starts a new paragraph, since
    the split below only touches non-blank-line-separated runs. A chunk
    that is a blockquote (starts with ">") is left alone: split_quote_
    attribution already gives it its own internal blank-"> "-line structure
    for the quote/attribution split, and this must not interfere with
    that."""
    pieces = re.split(r"(\n\s*\n)", md)
    out = []
    for piece in pieces:
        if not piece.strip() or piece.lstrip("\n").startswith(">"):
            out.append(piece)
        else:
            out.append(piece.replace("\n", "  \n"))
    return "".join(out)


def split_text_blocks(raw_text):
    """TEXT as a list of {"kind": "markdown", "content"} and {"kind":
    "figure-row", "images"} blocks in source order, instead of one string,
    so the template can render a figure row as its own flex layout instead
    of markdown content. split_quote_attribution runs per markdown block
    (its regex only ever matches within one, and the figure row's own
    Image:/Caption:/Credit: lines must not be touched by it), then
    apply_hard_wraps, in that order so the blockquote's own attribution
    split already exists by the time apply_hard_wraps decides what to skip."""
    parts = FIGURE_ROW_RE.split(raw_text)
    blocks = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            content = apply_hard_wraps(split_quote_attribution(part.strip("\n")))
            if content.strip():
                blocks.append({"kind": "markdown", "content": content})
        else:
            blocks.append({"kind": "figure-row", "images": parse_figure_row_block(part)})
    return blocks


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


def has_math(blocks, technical):
    text_parts = [b["content"] for b in blocks if b["kind"] == "markdown"]
    for b in blocks:
        if b["kind"] == "figure-row":
            text_parts.extend(f["caption"] for f in b["images"])
    text_parts.append(technical or "")
    return any("$" in t for t in text_parts)


def resolve_card_credit(card, banner, blocks):
    """Item 5: no visible credit on cards, but the thumbnail's title
    attribute carries the credit of whichever figure or banner uses the
    same original source photo, found by matching the card's own
    (un-overridden) source_stem against the banner's and every figure-row
    image's stem. Two targets can also point at the same original via a
    "<-- from original.jpg" comment without sharing a filename themselves
    (DUNE-Computing's card and banner are both cropped from the same photo
    under their own distinct names), so original_stem is checked too,
    whichever side carries it."""
    credit_by_stem = {}
    banner_image_stem = banner.get("single", "")
    if banner_image_stem and banner.get("credit"):
        credit_by_stem[banner_image_stem] = banner["credit"]
        if banner.get("original_stem"):
            credit_by_stem[banner["original_stem"]] = banner["credit"]
    for b in blocks:
        if b["kind"] == "figure-row":
            for fig in b["images"]:
                if fig.get("credit"):
                    credit_by_stem[fig["image"]] = fig["credit"]
    return (credit_by_stem.get(card["source_stem"])
            or credit_by_stem.get(card.get("original_stem"), ""))


def build_project(slug, path, converted_dir):
    sections = parse_sections(path.read_text(encoding="utf-8"))
    # BANNER is optional, like FIGURES: ATLAS has no pre-composed banner and
    # leads straight into its own [[FIGURE-ROW]] blocks instead.
    required = ["CARD", "LEFT PANEL", "PAGE HEADING", "TEXT", "TECHNICAL"]
    missing = [s for s in required if s not in sections]
    if missing:
        print(f"  ERROR {slug}: missing sections {missing}", file=sys.stderr)
        sys.exit(1)

    card = parse_card(sections["CARD"], slug, converted_dir)
    banner = parse_banner(sections.get("BANNER", ""), slug, converted_dir)
    panel = parse_panel(sections["LEFT PANEL"], card, slug, converted_dir)
    blocks = split_text_blocks(sections["TEXT"].strip())
    card["credit"] = resolve_card_credit(card, banner, blocks)
    technical = sections["TECHNICAL"].strip()
    figures = parse_figures(sections.get("FIGURES"))

    return {
        "slug": slug,
        "card": card,
        "banner": banner,
        "panel": panel,
        "page_heading": sections["PAGE HEADING"].strip(),
        "text": blocks,
        "figures": figures,
        "technical": technical,
        "has_math": has_math(blocks, technical),
    }


def collect_assets(*projects):
    """stem -> True for every image stem referenced by these projects."""
    stems = set()
    for p in projects:
        stems.add(p["card"]["image"])
        stems.update(p["banner"]["images"])
        if p["banner"].get("single"):
            stems.add(p["banner"]["single"])
        stems.update(p["figures"])
        stems.update(m["image"] for m in p["panel"]["team"])
        if p["panel"].get("logo"):
            stems.add(p["panel"]["logo"])
        for group in p["panel"]["links"]:
            for link in group:
                if link.get("kind") == "image":
                    stems.add(link["src"])
                    if link.get("dark_src"):
                        stems.add(link["dark_src"])
        for block in p["text"]:
            if block["kind"] == "figure-row":
                stems.update(f["image"] for f in block["images"])
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
            # an animated image's reduced-motion still: <stem>-still.webp
            # travels with it (see partials/research/picture.html)
            if files and by_stem.get(f"{s}-still"):
                files = files + by_stem[f"{s}-still"]
            if not files:
                report.append((p["slug"], s, "MISSING"))
                continue
            for f in files:
                shutil.copy2(f, dest_dir / f.name)
            report.append((p["slug"], s, ", ".join(f.name for f in files)))
    return report


def image_needs_frame(im):
    """True if the image's four corners are all light and opaque: a baked-in
    white/light background that would otherwise float uncarded against the
    page (see item 5, "check map_lhc_blue.png"), as opposed to a photo,
    whose corners are typically dark or busy. Checked by sampling, not
    guessed from the filename, so the rule generalises to any future
    figure-row image rather than hardcoding one stem."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        r, g, b, a = rgba.getpixel((x, y))
        if a < 250 or min(r, g, b) < 225:
            return False
    return True


def attach_figure_row_sizes(projects):
    """Once copy_assets has placed the final files, read each figure-row
    image's actual pixel size from assets/research/<slug>/ and store
    width/height/ratio on it: the template's "flex: <ratio> 1 0" trick
    (equal-height row, no cropping) needs the ratio, and the build report
    wants the raw pixel sizes. Also stores needs_frame (see
    image_needs_frame), so a single-image row with a busy/dark photo and one
    with a baked-light background are told apart automatically."""
    from PIL import Image as PILImage

    sizes = []
    for p in projects:
        dest_dir = ASSETS_OUT / p["slug"]
        for block in p["text"]:
            if block["kind"] != "figure-row":
                continue
            for fig in block["images"]:
                path = None
                for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    candidate = dest_dir / f"{fig['image']}{ext}"
                    if candidate.exists():
                        path = candidate
                        break
                if not path:
                    print(f"  WARNING: figure-row image not found for {p['slug']}/{fig['image']}", file=sys.stderr)
                    continue
                with PILImage.open(path) as im:
                    w, h = im.width, im.height
                    frame = image_needs_frame(im)
                fig["width"] = w
                fig["height"] = h
                fig["ratio"] = round(w / h, 6)
                fig["needs_frame"] = frame
                sizes.append((p["slug"], fig["image"], w, h, frame))
    return sizes


def discover_projects(theme_dir):
    """A DUNE-style theme's project slugs: every subdirectory with its own
    _content.txt, sorted by an optional "Order:" line in its == CARD ==
    (lower first), folders without one sorting after those that have one,
    alphabetically among themselves either way."""
    slugs = sorted(d.name for d in theme_dir.iterdir()
                   if d.is_dir() and (d / "_content.txt").exists())

    def order_key(slug):
        content = (theme_dir / slug / "_content.txt").read_text(encoding="utf-8")
        kv = parse_kv(parse_sections(content).get("CARD", ""))
        order = kv.get("Order")
        return (int(order) if order else 999, slug)

    return sorted(slugs, key=order_key)


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

    themes_out = []
    all_projects = []
    figure_row_sizes = []

    for theme_def in THEME_DEFS:
        theme_dir = args.src / theme_def["folder"]
        if not theme_dir.is_dir():
            print(f"ERROR: theme folder {theme_dir} not found", file=sys.stderr)
            sys.exit(1)

        intro_path = theme_dir / "_intro.txt"
        intro_raw = intro_path.read_text(encoding="utf-8").strip() if intro_path.exists() else ""
        converted = theme_dir / "_converted"

        slugs = theme_def["slugs"] or discover_projects(theme_dir)
        projects = []
        for slug in slugs:
            content = theme_dir / slug / "_content.txt"
            if not content.exists():
                print(f"ERROR: {content} not found", file=sys.stderr)
                sys.exit(1)
            projects.append(build_project(slug, content, converted if converted.is_dir() else None))

        themes_out.append({
            "id": theme_def["id"],
            "title": theme_def["title"],
            "intro": parse_inline_segments(intro_raw) if intro_raw else [],
            "projects": projects,
        })
        all_projects.extend(projects)

        print(f"\ntheme {theme_def['id']}: {len(projects)} project(s)")
        for p in projects:
            banner_desc = f"single({p['banner']['single']})" if p['banner'].get('single') else f"{len(p['banner']['images'])} image(s)"
            print(f"  {p['slug']:14} math={p['has_math']!s:5}  "
                  f"team={len(p['panel']['team'])}  links={sum(len(g) for g in p['panel']['links'])}  "
                  f"banner={banner_desc}  figures={len(p['figures'])}")

        if converted.is_dir():
            print(f"  copying assets from {converted}")
            for slug, s, result in copy_assets(converted, projects):
                marker = "  MISSING" if result == "MISSING" else ""
                print(f"    {slug:14} {s:32} -> {result}{marker}")
            figure_row_sizes.extend(attach_figure_row_sizes(projects))
        else:
            print(f"  WARNING: {converted} not found, no assets copied", file=sys.stderr)

    data = {"themes": themes_out}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_content_pages(all_projects)

    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(all_projects)} project(s) across {len(themes_out)} theme(s)")
    if figure_row_sizes:
        print("\nfigure-row image sizes:")
        for slug, img, w, h, frame in figure_row_sizes:
            warn = "  WARNING: under 820px wide" if w < 820 else ""
            frame_note = "  framed (light bg)" if frame else ""
            print(f"  {slug:14} {img:32} {w}x{h}{warn}{frame_note}")


if __name__ == "__main__":
    main()
