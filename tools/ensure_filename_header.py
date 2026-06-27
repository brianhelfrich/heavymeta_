# heavymetal/tools/ensure_filename_header.py
#!/usr/bin/env python3
import pathlib
import re
import subprocess
import sys

COMMENT_STYLES = {
    ".py": "# {path}",
    ".html": "<!-- {path} -->",
    ".js": "// {path}",
    ".css": "/* {path} */",
    ".sh": "# {path}",
}


def get_repo_root() -> pathlib.Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
        return pathlib.Path(out)
    except Exception:
        return pathlib.Path.cwd()


REPO_ROOT = get_repo_root()
REPO_NAME = REPO_ROOT.name  # e.g. "heavymetal"


def build_header(p: pathlib.Path) -> tuple[str, str]:
    ext = p.suffix.lower()
    style = COMMENT_STYLES.get(ext)
    if not style:
        return "", ""
    rel = (
        p.resolve().relative_to(REPO_ROOT).as_posix()
    )  # e.g. "backend/__init__.py" or "run.py"
    path_with_repo = f"{REPO_NAME}/{rel}"  # e.g. "heavymetal/backend/__init__.py" or "heavymetal/run.py"
    return style, style.format(path=path_with_repo)


def normalize_line_endings(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def ensure_header(p: pathlib.Path) -> int:
    if not p.is_file():
        return 0
    style, wanted = build_header(p)
    if not style:
        return 0

    try:
        text = normalize_line_endings(p.read_text(encoding="utf-8"))
    except Exception:
        return 0

    # If already correct, nothing to do
    if text.startswith(wanted):
        return 0

    lines = text.split("\n")
    first = lines[0] if lines else ""

    # Regex to detect a same-style header on line 1 (wrong path, missing repo name, etc.)
    # Examples it will replace:
    #   "# run.py" / "# backend/__init__.py" / "<!-- run.py -->" / "// script.js" / "/* style.css */"
    wrong_header_patterns = {
        "#": r"^#\s+(.+)$",
        "//": r"^//\s+(.+)$",
        "/*": r"^/\*\s+(.+)\s+\*/$",
        "<!--": r"^<!--\s+(.+)\s+-->$",
    }

    # Map style prefix to regex key
    if style.startswith("#"):
        key = "#"
    elif style.startswith("//"):
        key = "//"
    elif style.startswith("/*"):
        key = "/*"
    elif style.startswith("<!--"):
        key = "<!--"
    else:
        key = None

    if key:
        m = re.match(wrong_header_patterns[key], first.strip())
        if m:
            existing_path = m.group(1)
            # If the existing header doesn't already start with the repo name, replace it
            if not existing_path.startswith(f"{REPO_NAME}/"):
                lines[0] = wanted
                p.write_text("\n".join(lines), encoding="utf-8")
                return 1
            # If it starts with repo name but is different for some reason, also replace
            if existing_path != wanted.replace(
                style.split("{")[0].strip() + " ", ""
            ).strip("*/-! "):
                lines[0] = wanted
                p.write_text("\n".join(lines), encoding="utf-8")
                return 1

    # Otherwise, prepend the correct header
    p.write_text(wanted + "\n" + text, encoding="utf-8")
    return 1


if __name__ == "__main__":
    changed = 0
    for arg in sys.argv[1:]:
        changed += ensure_header(pathlib.Path(arg))
    # Always exit 0 so the hook can re-stage changed files
    sys.exit(0)
