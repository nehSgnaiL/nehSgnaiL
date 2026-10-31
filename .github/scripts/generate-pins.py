"""Render public repo data from GitHub Stats Extended in GitHub's pin layout."""

from html import escape
from html.parser import HTMLParser
from dataclasses import dataclass
from pathlib import Path
import re
import textwrap
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
NS = {"svg": "http://www.w3.org/2000/svg"}
OUTPUT = ROOT / "dist" / "pins"
PALETTES = {
    "light": ("#0969da", "#59636e", "#d1d9e0"),
    "dark": ("#4493f8", "#9198a1", "#3d444d"),
}
FONT_STACK = ('"Mona Sans VF", -apple-system, system-ui, "Segoe UI", '
              '"Noto Sans Backtick Fix", "Noto Sans", Helvetica, Arial, sans-serif, '
              '"Apple Color Emoji", "Segoe UI Emoji"')


@dataclass(frozen=True)
class Pin:
    owner: str
    repo: str
    stem: str


class PinLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.pins = {}
        self.stems = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.href = attrs.get("href")
        if tag != "img" or not self.href:
            return
        image = Path(unquote(urlsplit(attrs.get("src", "")).path))
        if image.parent.name != "pins":
            return
        filename = re.fullmatch(r"([\w.-]+)-(light|dark)\.svg", image.name, re.ASCII)
        target = urlsplit(self.href)
        repository = re.fullmatch(r"/([\w.-]+)/([\w.-]+)/?", unquote(target.path), re.ASCII)
        if not filename or target.scheme != "https" or target.hostname != "github.com" or not repository:
            raise ValueError(f"Invalid repository pin link: {self.href}")
        owner, repo = repository.groups()
        stem, theme = filename.groups()
        if target.fragment and target.fragment != f"gh-{theme}-mode-only":
            raise ValueError(f"Pin theme does not match its image: {self.href}")
        key = (owner.lower(), repo.lower())
        pin = Pin(owner, repo, stem)
        if key in self.pins and self.pins[key].stem != stem:
            raise ValueError(f"Light/dark pin filenames must share a stem: {owner}/{repo}")
        if stem in self.stems and self.stems[stem] != key:
            raise ValueError(f"Different repositories must use different pin filenames: {stem}")
        self.pins.setdefault(key, pin)
        self.stems[stem] = key

    def handle_endtag(self, tag):
        if tag == "a":
            self.href = None


def read_pins(readme):
    parser = PinLinks()
    parser.feed(readme)
    return list(parser.pins.values())


def text_width(text, size=12):
    # Helvetica advance widths keep SVG wrapping independent of installed fonts.
    widths = dict(zip("abcdefghijklmnopqrstuvwxyz", (
        556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833,
        556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500,
    )))
    widths.update({" ": 278, "-": 333, ".": 278, ",": 278, "I": 278,
                   "L": 556, "P": 667, "A": 667, "T": 611, "S": 667})
    return sum(widths.get(char, 556) for char in text) * size / 1000


def fetch(owner, repo):
    query = urlencode({"username": owner, "repo": repo, "card_width": 400})
    with urlopen(f"https://github-stats-extended.vercel.app/api/pin?{query}", timeout=60) as response:
        root = ET.fromstring(response.read())

    def by_id(name):
        return root.find(f".//*[@data-testid='{name}']")

    if by_id("header") is None or (by_id("header").text or "").casefold() != repo.casefold():
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
        icons[name] = {
            "d": path.attrib["d"],
            "fill-rule": path.attrib.get("fill-rule", "nonzero"),
        }
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
  </style>
  <rect x="8.5" y="0.5" width="391" height="{height - 1}" rx="6" fill="none" stroke="{border}"/>
''']

    def icon(name, x, y):
        shape = data["icons"][name]
        parts.append(
            f'  <path transform="translate({x} {y})" fill="{muted}" '
            f'fill-rule="{escape(shape["fill-rule"], quote=True)}" '
            f'd="{escape(shape["d"], quote=True)}"/>\n'
        )

    icon("repo", 25, 19)
    parts.append(f'  <text class="name" x="45" y="31">{escape(repo)}</text>\n')
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
    pins = read_pins((ROOT / "README.md").read_text())
    data = {pin: fetch(pin.owner, pin.repo) for pin in pins}
    rendered = {}
    for start in range(0, len(pins), 2):
        row = pins[start:start + 2]
        height = 89 + 18 * max(len(wrap(data[pin]["description"])) for pin in row)
        for pin in row:
            for theme in PALETTES:
                rendered[f"{pin.stem}-{theme}.svg"] = render(pin.repo, data[pin], theme, height)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.svg"):
        if old.name not in rendered:
            old.unlink()
    for filename, svg in rendered.items():
        ET.fromstring(svg)
        (OUTPUT / filename).write_text(svg)


if __name__ == "__main__":
    main()
