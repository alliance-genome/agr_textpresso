"""Build a searchable index of Textpresso ontology categories from OBO files.

Used by cas_annotate_server.py's /v1/textpresso/category_search endpoint to
let clients look up the exact stored category string (e.g. "seed
(PO:0009010)") that --category requires, instead of guessing.

Reads the same OBO files the annotator/indexer were built from -- the set
listed in ontology.conf, under obofiles4production/ -- and reconstructs each
category's canonical string exactly as it's stored in the Lucene index:
"<name> (<id>)". Regex patterns for OBO [Term] blocks are lifted from
bin/ontology_synonym_audit.py (sorghumbase_textpresso_implementation repo),
which already parses this same format for a different purpose.
"""

import os
import re

ONTOLOGY_CONF_DEFAULT = "/usr/local/etc/ontology.conf"
OBO_DIR_DEFAULT = "/data/textpresso/obofiles4production"

_STANZA_RE = re.compile(r"^\[(\S+)\]\s*$")
_ID_RE = re.compile(r"^id:\s*(\S+)")
_NAME_RE = re.compile(r"^name:\s*(.*)$")
_SYN_RE = re.compile(r'^synonym:\s*"([^"]*)"')
_OBSOLETE_RE = re.compile(r"^is_obsolete:\s*true\b")


def _iter_obo_terms(obo_path):
    """Yield {id, name, synonyms} for each non-obsolete [Term] block in an OBO file."""
    stanza = None
    term_id = term_name = None
    synonyms = []
    obsolete = False

    def _flush():
        if stanza == "Term" and term_id and term_name and not obsolete:
            return {"id": term_id, "name": term_name, "synonyms": synonyms}
        return None

    with open(obo_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _STANZA_RE.match(line)
            if m:
                rec = _flush()
                if rec:
                    yield rec
                stanza = m.group(1)
                term_id = term_name = None
                synonyms = []
                obsolete = False
                continue
            if stanza != "Term":
                continue
            m = _ID_RE.match(line)
            if m:
                term_id = m.group(1)
                continue
            m = _NAME_RE.match(line)
            if m:
                term_name = m.group(1)
                continue
            m = _SYN_RE.match(line)
            if m:
                synonyms.append(m.group(1))
                continue
            if _OBSOLETE_RE.match(line):
                obsolete = True
    rec = _flush()
    if rec:
        yield rec


def _active_obo_paths(ontology_conf=ONTOLOGY_CONF_DEFAULT, obo_dir=OBO_DIR_DEFAULT):
    """Return the list of OBO file paths listed in ontology.conf.

    Each line's first whitespace-separated token is the OBO path (remaining
    tokens are subset names, e.g. "go.obo 6 goslim_generic ..."). Falls back
    to every *.obo in obo_dir if ontology.conf isn't readable, so the index
    still builds (possibly over-inclusive) rather than coming up empty.
    """
    try:
        with open(ontology_conf) as fh:
            paths = [line.split()[0] for line in fh if line.strip()]
        if paths:
            return paths
    except OSError:
        pass
    import glob
    return sorted(glob.glob(os.path.join(obo_dir, "*.obo")))


def build_index(ontology_of, ontology_conf=ONTOLOGY_CONF_DEFAULT, obo_dir=OBO_DIR_DEFAULT):
    """Build the category index.

    ontology_of -- casannot._ontology_of, so a category string ("name (id)")
    gets classified into GO/PO/TO/MAIZE_GENES/OTHER exactly the same way an
    actual CAS2 annotation would be, for consistency.

    Returns {"categories": [...], "synonyms": {lowercased_text: [record, ...]}}
    where each record is {"id", "name", "category", "ontology"}.
    """
    categories = []
    synonym_index = {}
    seen_ids = set()

    for obo_path in _active_obo_paths(ontology_conf, obo_dir):
        if not os.path.exists(obo_path):
            continue
        for term in _iter_obo_terms(obo_path):
            if term["id"] in seen_ids:
                continue
            seen_ids.add(term["id"])
            category = f"{term['name']} ({term['id']})"
            record = {
                "id": term["id"],
                "name": term["name"],
                "category": category,
                "ontology": ontology_of(category),
            }
            categories.append(record)
            for syn in term["synonyms"]:
                synonym_index.setdefault(syn.lower(), []).append(record)

    return {"categories": categories, "synonyms": synonym_index}


def search(index, query, ontology_filter=None, limit=20):
    """Rank category matches for a free-text query.

    Match quality, best first: exact name/id/category match, name starts
    with query, exact synonym match, name contains query, synonym contains
    query. Deduplicates by category id (keeps the best rank seen), then
    sorts by (rank, name) and truncates to limit.
    """
    q = query.strip().lower()
    if not q:
        return []

    best = {}  # id -> (rank, record, matched_on)

    def _consider(rec, rank, matched_on):
        rid = rec["id"]
        if rid not in best or rank < best[rid][0]:
            best[rid] = (rank, rec, matched_on)

    for rec in index["categories"]:
        name_l = rec["name"].lower()
        if name_l == q or rec["id"].lower() == q or rec["category"].lower() == q:
            _consider(rec, 0, "exact")
        elif name_l.startswith(q):
            _consider(rec, 1, "name_prefix")
        elif q in name_l:
            _consider(rec, 3, "name_substring")

    for syn_text, recs in index["synonyms"].items():
        if syn_text == q:
            for rec in recs:
                _consider(rec, 2, "synonym_exact")
        elif q in syn_text:
            for rec in recs:
                _consider(rec, 4, "synonym_substring")

    results = list(best.values())
    if ontology_filter:
        results = [r for r in results if r[1]["ontology"] in ontology_filter]
    results.sort(key=lambda r: (r[0], r[1]["name"]))

    return [
        {"id": rec["id"], "name": rec["name"], "category": rec["category"],
         "ontology": rec["ontology"], "matched_on": matched_on}
        for _, rec, matched_on in results[:limit]
    ]
