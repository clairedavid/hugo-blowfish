#!/usr/bin/env python3
"""Turn cv-source/CV_Claire_David.tex into data/cv.json.

The .tex is the source of truth: edit it, re-run this, rebuild the site. The
JSON it writes is what layouts/shortcodes/cv.html renders, so the page never
parses LaTeX at build time.

The CV's structure is simple and regular:
    \\section{TITLE}            a top-level section
    \\h{Subtitle}               a group heading inside a section
    \\suprow{date}{content}     a two-column entry, and likewise \\cvrow and
    \\pubrow                    \\pubrow; they differ only in column widths

Inside an entry's content, \\newline separates lines, \\textbf marks the entry
title and \\light the muted detail lines. Each line is emitted as a small,
already-escaped HTML fragment, because lines routinely mix bold, muted, links
and superscripts, and carrying that as nested data would be heavier to render
than to read.

Usage:  python3 scripts/build-cv-data.py
"""
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEX = ROOT / "cv-source" / "CV_Claire_David.tex"
OUT = ROOT / "data" / "cv.json"

# Section titles as they should read on the page, keyed by the .tex's uppercase
# form. Order here is the order on the page.
TITLES = [
    ("EDUCATION", "Education"),
    ("APPOINTMENTS", "Appointments"),
    ("PROFESSIONAL DEVELOPMENT", "Professional Development"),
    ("SKILLS", "Skills"),
    ("RESEARCH", "Research"),
    ("ENGINEERING EXPERIENCE", "Engineering Experience"),
    ("RESEARCH SUPERVISION", "Research Supervision"),
    ("TEACHING EXPERIENCE", "Teaching Experience"),
    ("STUDENT PLACEMENT", "Student Placement"),
    ("ACADEMIC SERVICE", "Academic Service"),
    ("GRANTS & AWARDS", "Grants & Awards"),
    ("PRESENTATIONS", "Presentations"),
    ("PUBLICATIONS", "Publications"),
    ("PROCEEDINGS", "Proceedings"),
    ("OTHER ACTIVITIES", "Other Activities"),
]

# LaTeX accents map onto combining marks, then NFC composes them: \^a -> â.
# Handled generally rather than as a lookup table, so an accent that has not
# appeared in the CV before still comes out right.
ACCENT_COMB = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308",
    "~": "\u0303", "=": "\u0304", ".": "\u0307",
    "u": "\u0306", "v": "\u030c", "H": "\u030b",
    "c": "\u0327", "k": "\u0328", "d": "\u0323", "b": "\u0331", "r": "\u030a",
}
LIGATURES = {r"\ss": "\u00df", r"\ae": "\u00e6", r"\oe": "\u0153",
             r"\o": "\u00f8", r"\l": "\u0142", r"\aa": "\u00e5"}


def accents(s):
    def rep(m):
        comb = ACCENT_COMB.get(m.group(1))
        return unicodedata.normalize("NFC", m.group(2) + comb) if comb else m.group(2)
    # symbol accents are safe unbraced: those characters never start a command
    s = re.sub(r"\\(['`^\"~=.])\s*\{([A-Za-z])\}", rep, s)
    s = re.sub(r"\\(['`^\"~=.])\s*([A-Za-z])", rep, s)
    # letter accents only in braced form, or they would eat \usepackage etc.
    s = re.sub(r"\\([uvHckdbr])\s*\{([A-Za-z])\}", rep, s)
    for k, v in LIGATURES.items():
        s = re.sub(re.escape(k) + r"(?![a-zA-Z])", v, s)
    return s


def strip_comments(text):
    """Drop LaTeX comments, keeping escaped \\% intact."""
    out = []
    for line in text.split("\n"):
        res, i = [], 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                break
            res.append(line[i])
            i += 1
        out.append("".join(res))
    return "\n".join(out)


def match_brace(s, i):
    """Given index of '{', return index just past its matching '}'."""
    depth = 0
    while i < len(s):
        if s[i] == "{" and (i == 0 or s[i - 1] != "\\"):
            depth += 1
        elif s[i] == "}" and s[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def read_args(s, i, n):
    """Read n brace-delimited arguments starting at i. Returns (args, end)."""
    args = []
    for _ in range(n):
        while i < len(s) and s[i] in " \t\n":
            i += 1
        if i >= len(s) or s[i] != "{":
            args.append("")
            continue
        end = match_brace(s, i)
        args.append(s[i + 1:end - 1])
        i = end
    return args, i


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


MATHSYM = {
    r"\\cdot": "\u00b7", r"\\rightarrow": "\u2192", r"\\to": "\u2192",
    r"\\hbar": "\u210f", r"\\times": "\u00d7", r"\\pm": "\u00b1",
    r"\\alpha": "\u03b1", r"\\beta": "\u03b2", r"\\mu": "\u03bc",
    r"\\nu": "\u03bd", r"\\gamma": "\u03b3", r"\\sqrt": "\u221a",
}


def math(expr):
    """Render the CV's inline math without a maths engine. The CV only uses a
    dozen symbols, \\bar accents and simple sub/superscripts, so they map
    straight onto Unicode: \\bar{b} becomes b followed by a combining macron."""
    s = expr
    s = re.sub(r"\\bm\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:mathrm|mathit|text)\s*\{([^{}]*)\}", r"\1", s)
    # \bar{x} -> x + combining macron
    s = re.sub(r"\\bar\s*\{([^{}]*)\}", lambda m: m.group(1) + "\u0304", s)
    s = re.sub(r"\\bar\s*([A-Za-z])", lambda m: m.group(1) + "\u0304", s)
    s = re.sub(r"\^\s*\{([^{}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"_\s*\{([^{}]*)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"\^([A-Za-z0-9])", r"<sup>\1</sup>", s)
    s = re.sub(r"_([A-Za-z0-9])", r"<sub>\1</sub>", s)
    for k, v in MATHSYM.items():
        s = re.sub(k + r"(?![a-zA-Z])", v, s)
    s = s.replace("\\,", "\u2009").replace("\\;", "\u2009").replace("\\!", "")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def inline(tex):
    """LaTeX inline markup -> a small HTML fragment."""
    s = tex
    # inline maths first: its braces and commands must not reach the generic
    # stripping below, which would leave "$$" where a symbol used to be
    s = re.sub(r"\$([^$]*)\$", lambda m: math(m.group(1)), s)

    # commands that carry content we keep, innermost first via repeated passes
    def repl_cmd(s, name, fmt):
        out, i = [], 0
        tok = "\\" + name
        while True:
            j = s.find(tok, i)
            # make sure it is the whole command name, not a prefix
            while j != -1 and j + len(tok) < len(s) and (s[j + len(tok)].isalpha()):
                j = s.find(tok, j + 1)
            if j == -1:
                out.append(s[i:])
                break
            out.append(s[i:j])
            args, end = read_args(s, j + len(tok), fmt[0])
            out.append(fmt[1](*[inline(a) for a in args]))
            i = end
        return "".join(out)

    # links first, so their text is not mangled
    s = repl_cmd(s, "href", (2, lambda u, t: f'<a href="{u}" target="_blank" rel="noopener">{t}</a>'))
    s = repl_cmd(s, "url", (1, lambda u: f'<a href="{u}" target="_blank" rel="noopener">{u}</a>'))
    s = repl_cmd(s, "textbf", (1, lambda t: f"<strong>{t}</strong>"))
    s = repl_cmd(s, "textit", (1, lambda t: f"<em>{t}</em>"))
    s = repl_cmd(s, "emph", (1, lambda t: f"<em>{t}</em>"))
    s = repl_cmd(s, "textsuperscript", (1, lambda t: f"<sup>{t}</sup>"))
    s = repl_cmd(s, "light", (1, lambda t: f'<span class="cv-muted">{t}</span>'))
    s = repl_cmd(s, "tagg", (1, lambda t: f'<span class="cv-tag">{t}</span>'))
    s = repl_cmd(s, "tag", (1, lambda t: f'<span class="cv-tag">{t}</span>'))
    s = repl_cmd(s, "textcolor", (2, lambda c, t: t))
    s = repl_cmd(s, "colorbox", (2, lambda c, t: t))
    s = repl_cmd(s, "mbox", (1, lambda t: t))
    s = repl_cmd(s, "text", (1, lambda t: t))

    # drop formatting-only commands and their braces
    for name in ("small", "footnotesize", "normalsize", "sffamily", "bfseries",
                 "itshape", "centering", "noindent", "par", "hfill", "vfill"):
        s = s.replace("\\" + name, "")
    s = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)

    s = s.replace(r"\tdot", " &middot; ")
    s = s.replace(r"\,--\,", "\u2009\u2013\u2009").replace(r"\,-\,", "\u2009\u2013\u2009")
    s = s.replace("---", "\u2013").replace("--", "\u2013")   # never an em dash
    # \ldots: LaTeX swallows the space after a command, so a following word
    # gets one back here ("impacts\ldots you" reads "impacts\u2026 you")
    s = re.sub(r"\\l?dots(?![a-zA-Z])\s*(?=[A-Za-z0-9])", "\u2026 ", s)
    s = re.sub(r"\\l?dots(?![a-zA-Z])\s*", "\u2026", s)
    s = accents(s)
    s = s.replace(r"\&", "&amp;").replace(r"\%", "%").replace(r"\_", "_")
    s = s.replace(r"\#", "#").replace(r"\$", "$")
    s = s.replace("~", "\u00a0")
    # LaTeX quoting, and the escaped inter-word space in "Prof.\ Aaron"
    s = s.replace("``", "\u201c").replace("''", "\u201d").replace("`", "\u2018")
    s = re.sub(r"\\ ", " ", s)
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)      # any leftover bare command
    s = re.sub(r"\\(.)", r"\1", s)            # any other escaped character
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"[ \t\n]+", " ", s).strip()
    return s


def split_lines(content):
    """Split an entry's content on \\newline into HTML lines."""
    parts = re.split(r"\\newline|\\\\", content)
    lines = []
    for p in parts:
        h = inline(p)
        if h:
            lines.append(h)
    return lines


ROW_RE = re.compile(r"\\(suprow|cvrow|pubrow)\s*")


def parse_blocks(body):
    """Parse a section (or group) body into entries, in document order."""
    entries, i = [], 0
    while True:
        m = ROW_RE.search(body, i)
        if not m:
            break
        args, end = read_args(body, m.end(), 2)
        date_raw, content = args
        entry = {"date": "", "duration": "", "lines": split_lines(content)}
        # \datemonths{2010}{5 months} is a year with a duration under it. Kept
        # as two fields so the page can centre the year and set the duration on
        # its own line, rather than running them together as "20105 months".
        dm = re.match(r"\s*\\datemonths\s*\{", date_raw)
        if dm:
            parts, _ = read_args(date_raw, dm.end() - 1, 2)
            entry["date"] = inline(parts[0])
            entry["duration"] = inline(parts[1])
        else:
            entry["date"] = inline(date_raw)
        entries.append(entry)
        i = end
    return entries


def cap_first(html_frag):
    """Upper-case the first visible character of an HTML fragment."""
    m = re.search(r">?([^<>])", html_frag)
    for i, ch in enumerate(html_frag):
        if ch == "<":
            j = html_frag.find(">", i)
            if j == -1:
                break
            continue
        if ch.isalpha():
            return html_frag[:i] + ch.upper() + html_frag[i + 1:]
        if ch not in " \t":
            break
    return html_frag


def parse_skills(body):
    """Skills is written as plain \\textbf{Label:} value lines, not row macros.
    The label becomes the left column so it reuses the same two-column render.
    Everything from \\vfill on is the PDF's inline page navigator, not CV
    content, so it is cut."""
    body = body.split("\\vfill")[0]
    entries = []
    for m in re.finditer(r"\\textbf\s*\{", body):
        e = match_brace(body, m.end() - 1)
        label = inline(body[m.end():e - 1]).rstrip(":").strip()
        nxt = body.find("\\textbf", e)
        rest = body[e:nxt if nxt != -1 else len(body)]
        rest = re.sub(r"\\\\\[[^\]]*\]", "", rest)
        val = inline(rest)
        if label and val:
            # Online CV only: the .tex reads "Communication: university-level
            # ..." inline, which needs no capital; as a standalone cell it does.
            # First character only, so "AI", "C++" and the rest are untouched.
            val = cap_first(val)
            entries.append({"date": label, "duration": "", "lines": [val]})
    return entries


def main():
    tex = strip_comments(TEX.read_text(encoding="utf-8"))

    # locate sections by their \section{...} in document order
    marks = []
    for m in re.finditer(r"\\section\s*\{", tex):
        end = match_brace(tex, m.end() - 1)
        title = inline(tex[m.end():end - 1]).replace("&amp;", "&")
        marks.append((m.start(), end, title))

    want = dict(TITLES)
    order = [t for _, t in TITLES]
    found = {}
    for idx, (start, end, title) in enumerate(marks):
        if title.upper() not in want:
            continue
        stop = marks[idx + 1][0] if idx + 1 < len(marks) else len(tex)
        found[want[title.upper()]] = tex[end:stop]

    missing = [t for t in order if t not in found]
    if missing:
        print("MISSING SECTIONS:", missing, file=sys.stderr)
        sys.exit(1)

    sections = []
    for title in order:
        body = found[title]
        sid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        # split into groups on \h{...}
        hs = []
        for m in re.finditer(r"\\h\s*\{", body):
            e = match_brace(body, m.end() - 1)
            hs.append((m.start(), e, inline(body[m.end():e - 1])))
        groups = []
        if hs:
            lead = parse_blocks(body[:hs[0][0]])
            if lead:
                groups.append({"heading": "", "entries": lead})
            for k, (s0, e0, h) in enumerate(hs):
                stop = hs[k + 1][0] if k + 1 < len(hs) else len(body)
                groups.append({"heading": h, "entries": parse_blocks(body[e0:stop])})
        else:
            groups.append({"heading": "", "entries": parse_blocks(body)})
        if title == "Skills":
            groups = [{"heading": "", "entries": parse_skills(body)}]
        groups = [g for g in groups if g["entries"]]
        sections.append({"id": sid, "title": title, "groups": groups})

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"sections": sections}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    ne = sum(len(g["entries"]) for s in sections for g in s["groups"])
    nl = sum(len(e["lines"]) for s in sections for g in s["groups"] for e in g["entries"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(sections)} sections, "
          f"{sum(len(s['groups']) for s in sections)} groups, {ne} entries, {nl} lines")
    for s in sections:
        n = sum(len(g["entries"]) for g in s["groups"])
        print(f"  {s['title']:32} {len(s['groups']):2} group(s)  {n:3} entries")


if __name__ == "__main__":
    main()
