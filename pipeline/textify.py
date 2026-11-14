"""Wikitext -> clean sentences with their section heading. Pure functions; no database.

    sentences(wikitext) -> [(section, text), ...] in reading order
    normalise(text) / sentence_hash(text) / years(text)
"""
import hashlib, re

# Finnish abbreviations that end in a dot but do not end a sentence.
ABBREVIATIONS = {"esim", "mm", "ns", "n", "jne", "ks", "vrt", "ym", "yms", "tms", "ts", "nk", "eKr",
                 "jKr", "eaa", "jaa", "s", "v", "kl", "klo", "milj", "mrd", "ap", "ip", "os", "ent",
                 "kok", "prof", "tri", "toim", "suom", "engl", "ruots", "lat", "lyh", "synt", "k",
                 "kuol", "vuod", "St", "Dr", "Mr", "no", "nro", "puh", "ao", "em", "l", "kpl", "ca"}
DROP_LINKS = ("tiedosto:", "kuva:", "file:", "image:", "luokka:", "category:", "media:")
DROP_TAGS = {"ref", "references", "gallery", "math", "table", "div", "timeline", "imagemap",
             "score", "syntaxhighlight", "source", "pre", "nowiki", "graph", "mapframe"}
MIN_CHARS = 25
# Reference sections: book lists and links are not the article's claims.
SKIP_SECTIONS = re.compile(r"^(lähteet|lähdeluettelo|viitteet|kirjallisuutta|kirjallisuus|aiheesta muualla|"
                           r"katso myös|lisätietoja|lisää luettavaa|ulkoiset linkit|huomautukset)\b", re.I)
_CITATION = re.compile(r"ISBN|^[^.:]{2,80}\(\d{4}\)\s*:|\bs\. \d+[–-]?\d*\.?$")

# A sentence ends at . ! ? (optionally followed by a closing quote or bracket), then whitespace,
# then something that starts a new sentence: a capital letter, a digit or an opening quote.
_BOUNDARY = re.compile(r'(?<=[.!?])["»”)\]]?\s+(?=[A-ZÅÄÖ0-9"«“])')
_SPACES = re.compile(r"\s+")
_QUOTES = str.maketrans({"”": '"', "“": '"', "«": '"', "»": '"', "’": "'", "‘": "'", "–": "-", "—": "-"})
_YEAR = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)(?![.,]\d)")


def normalise(text):
    return _SPACES.sub(" ", text.translate(_QUOTES)).strip()


def sentence_hash(text):
    """20-byte SHA-1 of the normalised, case-folded sentence. Same text = same hash."""
    return hashlib.sha1(normalise(text).casefold().encode("utf-8")).digest()


def years(text):
    """Years a sentence talks about (1000-2099), for event time. [] when none."""
    return sorted({int(y) for y in _YEAR.findall(text)})


def split_sentences(paragraph):
    """Split one paragraph of plain text into sentences, keeping abbreviations together."""
    parts, out = _BOUNDARY.split(paragraph), []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out:
            last_word = re.search(r"([A-Za-zÅÄÖåäö]+)\.\W*$", out[-1])
            if last_word and last_word.group(1) in ABBREVIATIONS:
                out[-1] = f"{out[-1]} {part}"
                continue
        out.append(part)
    return out


def keep(sentence):
    """Real prose only: long enough, mostly letters, no leftover markup."""
    if len(sentence) < MIN_CHARS or not re.search(r"[A-Za-zÅÄÖåäö]{3}", sentence):
        return False
    if any(mark in sentence for mark in ("{{", "}}", "[[", "]]", "{|", "|}", "<", ">", "==")):
        return False
    if _CITATION.search(sentence):
        return False
    letters = sum(c.isalpha() for c in sentence)
    return letters >= 0.5 * len(sentence)


def plain_text(wikitext):
    """Strip wikitext to plain text with mwparserfromhell, keeping '== heading ==' lines."""
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)
    for tag in code.filter_tags(recursive=True):
        if str(tag.tag).strip().lower() in DROP_TAGS:
            try:
                code.remove(tag)
            except ValueError:
                pass
    for link in code.filter_wikilinks(recursive=True):
        if str(link.title).strip().lower().startswith(DROP_LINKS):
            try:
                code.remove(link)
            except ValueError:
                pass
    for template in code.filter_templates(recursive=False):
        try:
            code.remove(template)
        except ValueError:
            pass
    for heading in code.filter_headings(recursive=False):
        title = heading.title.strip_code().strip()
        code.replace(heading, f"\n@@SECTION@@ {title}\n")
    return code.strip_code(normalize=True, collapse=True)


def sentences(wikitext, strip=plain_text):
    """[(section, sentence), ...] in reading order. `strip` is swappable for tests."""
    out, section = [], ""
    for line in strip(wikitext).splitlines():
        line = line.strip()
        if line.startswith("@@SECTION@@"):
            section = line.removeprefix("@@SECTION@@").strip()[:255]
            continue
        if SKIP_SECTIONS.match(section):
            continue
        line = re.sub(r"^[*#:;]+\s*", "", line)            # list markers
        if not line or line.startswith(("|", "!", "{", "}")):
            continue
        for s in split_sentences(line):
            s = normalise(s)
            if keep(s):
                out.append((section, s))
    return out
