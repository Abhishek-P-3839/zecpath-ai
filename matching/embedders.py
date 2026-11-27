"""Day 12: turn text into vectors ("embeddings") so that similar meaning = similar vector.

Two interchangeable backends, both return L2-normalized numpy arrays (so dot product = cosine similarity):

    SentenceTransformerEmbedder  real neural embeddings (needs: pip install sentence-transformers)
    HashingEmbedder              offline fallback, numpy only. Knows skill synonyms and categories (Day 9)
                                 and groups of related words, so "ReactJS developer" ~ "frontend engineer".

get_embedder() picks the best one that is available, so the rest of the code never cares which is used.
"""
import hashlib
import math
import re

import numpy as np

from parsers import skill_extractor as _sx
from parsers.skill_taxonomy import SKILLS
from utils.logger import get_logger

log = get_logger(__name__)

_STOP = set("""a an the and or of to in on for with at by from as is are was were be been being this that these those it its
we you your our their they he she i will can may should would could must have has had do does did not no yes if then than so
such per via into over under about across within also etc other more most any all each both new using use used work working
experience experienced years year strong good great ability able team teams role job company candidate looking required""".split())

# words that mean nearly the same thing share a "concept" feature
_CONCEPTS = {
    "c_dev": "developer engineer programmer coder sde software",
    "c_build": "build built develop developed create created design designed implement implemented architect architected engineer engineered",
    "c_lead": "manage managed lead led supervise coordinate coordinated oversee oversaw mentor mentored",
    "c_analyze": "analyze analyse analysis analytics insight insights report reports reporting dashboard dashboards visualize forecast",
    "c_service": "api apis endpoint endpoints rest restful microservice microservices backend server",
    "c_ui": "ui frontend front-end interface responsive web website webapp spa",
    "c_data": "data database databases sql query queries etl pipeline warehouse",
    "c_hiring": "recruit recruiter recruitment hiring talent sourcing onboarding interview interviewing screening payroll hr",
    "c_sales": "sales selling revenue prospect prospecting client clients customer customers lead-generation",
    "c_cloud": "cloud aws azure gcp deploy deployed deployment devops infrastructure container containers",
    "c_test": "test testing tested qa quality automation bug bugs",
    "c_learn": "ml machine-learning model models training predict prediction ai neural",
    "c_market": "marketing seo campaign campaigns content social brand",
}
_WORD_TO_CONCEPT = {w: c for c, words in _CONCEPTS.items() for w in words.split()}


def _stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


class Embedder:
    name = "base"

    def encode(self, texts):
        raise NotImplementedError


class HashingEmbedder(Embedder):
    """Offline embedder: weighted feature hashing. Deterministic, no downloads, no training."""
    name = "hashing-offline"
    default_calibration = (0.05, 0.60)        # cosine at which a match counts as 0% / 100% (tuned later)

    def __init__(self, dims=2048):
        self.dims = dims

    def _features(self, text):
        """{feature_name: weight}"""
        feats = {}
        add = lambda key, w: feats.__setitem__(key, feats.get(key, 0.0) + w)
        text = text or ""
        for m in _sx._TERM_RE.finditer(text):                      # skills -> canonical name + category (Day 9 dictionary)
            key = _sx._key(m.group(1))
            if key in _sx._AMBIGUOUS:
                continue
            info = _sx._ALIAS_INDEX.get(key)
            if info:
                add("skill:" + info[0], 2.0)
                add("cat:" + SKILLS[info[0]][0], 0.5)
        words = [w for w in re.findall(r"[a-z][a-z0-9+#.\-]*", text.lower()) if w not in _STOP and len(w) > 1]
        stems = [_stem(w.strip(".-")) for w in words]
        for w in stems:
            add("w:" + w, 1.0)
            if w in _WORD_TO_CONCEPT:
                add(_WORD_TO_CONCEPT[w], 0.8)
        for a, b in zip(stems, stems[1:]):
            add(f"b:{a}_{b}", 0.6)
        return feats

    def encode(self, texts):
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        for i, text in enumerate(texts):
            for feat, weight in self._features(text).items():
                h = int.from_bytes(hashlib.md5(feat.encode()).digest()[:8], "big")
                out[i, h % self.dims] += (1.0 if (h >> 40) & 1 else -1.0) * (1 + math.log(weight + 1e-9) if weight >= 1 else weight)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


class SentenceTransformerEmbedder(Embedder):
    """Neural embeddings. First use downloads the model (~90 MB), then it works offline."""
    default_calibration = (0.15, 0.75)

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer      # raises ImportError if not installed
        self.model = SentenceTransformer(model_name)
        self.name = model_name.split("/")[-1]

    def encode(self, texts):
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)


def get_embedder(prefer="auto"):
    """'auto' -> neural model if available, else offline. 'offline' forces the fallback."""
    if prefer != "offline":
        try:
            emb = SentenceTransformerEmbedder()
            log.info("Using neural embeddings: %s", emb.name)
            return emb
        except Exception as exc:                                    # not installed, or no internet for the first download
            log.info("Neural embeddings unavailable (%s); using offline hashing embedder.", type(exc).__name__)
    return HashingEmbedder()
