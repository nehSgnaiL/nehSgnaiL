"""Render public repo data from GitHub Stats Extended in GitHub's pin layout."""

from html import escape
from pathlib import Path
import textwrap
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET


REPOS = (
    "awesome-scientific-figure",
    "awesome-academic-phrase",
    "paper-daily-feed",
    "LPA",
)
NS = {"svg": "http://www.w3.org/2000/svg"}
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "pins"
PALETTES = {
    "light": ("#0969da", "#59636e", "#d1d9e0"),
    "dark": ("#4493f8", "#9198a1", "#3d444d"),
}
FONT_STACK = ('"Mona Sans VF", -apple-system, system-ui, "Segoe UI", '
              '"Noto Sans Backtick Fix", "Noto Sans", Helvetica, Arial, sans-serif, '
              '"Apple Color Emoji", "Segoe UI Emoji"')


def text_width(text, size=12):
    # Helvetica advance widths keep SVG wrapping independent of installed fonts.
    widths = dict(zip("abcdefghijklmnopqrstuvwxyz", (
        556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833,
        556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500,
    )))
    widths.update({" ": 278, "-": 333, ".": 278, ",": 278, "I": 278,
                   "L": 556, "P": 667, "A": 667, "T": 611, "S": 667})
    return sum(widths.get(char, 556) for char in text) * size / 1000


def fetch(repo):
    query = urlencode({"username": "nehSgnaiL", "repo": repo, "card_width": 400})
    with urlopen(f"https://github-stats-extended.vercel.app/api/pin?{query}", timeout=60) as response:
        root = ET.fromstring(response.read())

    def by_id(name):
        return root.find(f".//*[@data-testid='{name}']")

    if by_id("header") is None or by_id("header").text != repo:
        raise ValueError(f"Stats API did not return the expected repository: {repo}")
    description = root.find(".//svg:text[@class='description']", NS)
    if description is None:
        raise ValueError(f"Missing description: {repo}")
    lines = ["".join(node.itertext()).strip() for node in description.findall("svg:tspan", NS)]
    language = by_id("lang-name")
    color = by_id("lang-color")
    icons = {}
    for name, test_id in (("repo", "card-title"), ("star", "stargazers"), ("fork", "forkcount")):
        if name == "repo":
            path = by_id(test_id).find(".//svg:path", NS)
        else:
            if by_id(test_id) is None:
                continue
            parent = next(node for node in root.iter() if by_id(test_id) in list(node))
            group = next(node for node in root.iter() if parent in list(node))
            path = group.find(".//svg:path", NS)
        icons[name] = path.attrib["d"]
    return {
        "description": " ".join(lines),
        "language": language.text if language is not None else None,
        "color": color.attrib["fill"] if color is not None else None,
        "stars": by_id("stargazers").text if by_id("stargazers") is not None else "0",
        "forks": by_id("forkcount").text if by_id("forkcount") is not None else "0",
        "icons": icons,
    }


def wrap(text, width=358):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate) * 1.14 > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        lines[1] = textwrap.shorten(" ".join(lines[1:]), width=58, placeholder="…")
    return lines[:2]


def render(repo, data, theme, height):
    title, muted, border = PALETTES[theme]
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="408" height="{height}" viewBox="0 0 408 {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(repo)}</title>
  <desc id="desc">{escape(data['description'])}</desc>
  <style>
    text {{ font-family: {FONT_STACK}; font-size: 12px; font-weight: 400; fill: {muted}; }}
    .name {{ font-size: 14px; font-weight: 600; fill: {title}; }}
    .badge {{ font-size: 11.9px; font-weight: 500; }}
  </style>
  <rect x="8.5" y="0.5" width="391" height="{height - 1}" rx="6" fill="none" stroke="{border}"/>
''']

    def icon(name, x, y):
        parts.append(f'  <path transform="translate({x} {y})" fill="{muted}" d="{data["icons"][name]}"/>\n')

    icon("repo", 25, 19)
    parts.append(f'  <text class="name" x="45" y="31">{escape(repo)}</text>\n')
    badge_x = min(342, 45 + text_width(repo, 14) * 1.16 + 8)
    parts.append(f'  <rect x="{badge_x:.1f}" y="18.5" width="48" height="19" rx="9.5" fill="none" stroke="{border}"/>\n')
    parts.append(f'  <text class="badge" x="{badge_x + 24:.1f}" y="32" text-anchor="middle">Public</text>\n')
    for i, line in enumerate(wrap(data["description"])):
        parts.append(f'  <text x="25" y="{58 + i * 18}">{escape(line)}</text>\n')
    x, y = 25, height - 17
    if data["language"]:
        parts.append(f'  <circle cx="{x + 6}" cy="{y - 4}" r="6" fill="{escape(data["color"], quote=True)}"/>\n')
        parts.append(f'  <text x="{x + 16}" y="{y}">{escape(data["language"])}</text>\n')
        x += 16 + text_width(data["language"]) + 16
    for key, name in (("stars", "star"), ("forks", "fork")):
        if data[key] == "0":
            continue
        icon(name, round(x, 1), y - 12)
        parts.append(f'  <text x="{x + 20:.1f}" y="{y}">{escape(data[key])}</text>\n')
        x += 20 + text_width(data[key]) + 16
    parts.append("</svg>\n")
    return "".join(parts)


def main():
    data = {repo: fetch(repo) for repo in REPOS}
    rendered = {}
    for start in (0, 2):
        row = REPOS[start:start + 2]
        height = 89 + 18 * max(len(wrap(data[repo]["description"])) for repo in row)
        for repo in row:
            for theme in PALETTES:
                rendered[f"{repo}-{theme}.svg"] = render(repo, data[repo], theme, height)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, svg in rendered.items():
        ET.fromstring(svg)
        (OUTPUT / filename).write_text(svg)


if __name__ == "__main__":
    main()
