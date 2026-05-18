"""
BTF – Analyse Sentiment NLP (Module C)
Dictionnaire adapté au contexte ouest-africain.
Scanner presse, réseaux sociaux, canaux locaux.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("btf.nlp")

# ─── DICTIONNAIRE SENTIMENT ADAPTÉ AFRIQUE DE L'OUEST ────────────────────────
POSITIVE_WORDS = {
    # Français général
    "hausse", "croissance", "bénéfice", "profit", "gain", "succès", "record",
    "positif", "fort", "solide", "robuste", "expansion", "développement",
    "investissement", "confiance", "dynamique", "progression", "augmentation",
    # Contexte UEMOA / Afrique
    "UEMOA", "BCEAO", "stabilité", "CFA", "franc", "partenariat", "accord",
    "BRVM", "cotation", "dividende", "résultats", "performance", "croissance",
    "Coris", "Sonatel", "Ecobank", "Orange", "contrat", "exportation",
    "récolte", "abondance", "surplus", "approvisionnement", "livraison",
    # Crypto/Finance
    "bull", "bullish", "pump", "breakout", "support", "adoption",
    "institutionnel", "ETF", "approbation", "partenariat", "intégration",
}

NEGATIVE_WORDS = {
    # Français général
    "baisse", "perte", "déficit", "crise", "chute", "effondrement", "risque",
    "négatif", "faible", "fragile", "contraction", "récession", "inflation",
    "dette", "faillite", "scandale", "fraude", "pénurie", "manque",
    # Contexte UEMOA / Afrique
    "insécurité", "conflit", "sanction", "embargo", "perturbation",
    "sécheresse", "inondation", "récolte", "mauvaise", "rupture", "blocage",
    "grève", "fermeture", "pénurie", "tension", "instabilité", "coup",
    "transitoire", "fermeture frontière", "taxe", "douane", "restriction",
    # Crypto/Finance
    "bear", "bearish", "dump", "crash", "hack", "exploit", "SEC", "régulation",
    "interdiction", "ban", "liquidation", "manipulation", "arnaque",
}

INTENSIFIERS = {
    "très": 1.5, "extrêmement": 2.0, "fortement": 1.5, "massivement": 2.0,
    "légèrement": 0.5, "peu": 0.5, "faiblement": 0.5, "énormément": 2.0,
}

NEGATORS = {"ne", "pas", "non", "jamais", "aucun", "sans", "ni"}

# Sources à scanner
NEWS_SOURCES = [
    "https://www.lefaso.net",
    "https://www.rfi.fr/fr/afrique-de-l-ouest/",
    "https://www.financialafrik.com",
    "https://www.abidjan.net",
    "https://www.sika-finance.com",    # BRVM spécialisé
]


@dataclass
class SentimentResult:
    score: float        # -1.0 à +1.0
    label: str          # positif / négatif / neutre
    confidence: float   # 0.0 à 1.0
    positive_count: int
    negative_count: int
    source_count: int
    keywords_found: list


class NLPSentimentAnalyzer:
    """
    Analyseur de sentiment NLP pour les marchés ouest-africains.
    Combine analyse lexicale et scoring contextuel.
    """

    @classmethod
    async def analyze(cls, symbol: str, language: str = "fr") -> dict:
        """
        Analyse le sentiment pour un symbole donné.
        Agrège les résultats de plusieurs sources.
        """
        texts = await cls._collect_texts(symbol)
        if not texts:
            return {"score": 0.0, "label": "neutre", "confidence": 0.0}

        results = [cls._analyze_text(text) for text in texts]
        avg_score = sum(r.score for r in results) / len(results)
        avg_confidence = sum(r.confidence for r in results) / len(results)
        all_keywords = list(set(kw for r in results for kw in r.keywords_found))

        if avg_score > 0.15:
            label = "positif"
        elif avg_score < -0.15:
            label = "négatif"
        else:
            label = "neutre"

        return {
            "score":      round(avg_score, 4),
            "label":      label,
            "confidence": round(avg_confidence, 4),
            "keywords":   all_keywords[:10],
            "source_count": len(texts),
        }

    @classmethod
    def _analyze_text(cls, text: str) -> SentimentResult:
        """Analyse lexicale d'un texte avec gestion des négateurs et intensificateurs."""
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)

        positive_count = 0
        negative_count = 0
        score = 0.0
        keywords_found = []

        for i, word in enumerate(words):
            # Vérifier négateur dans fenêtre [-3, 0]
            window_start = max(0, i - 3)
            window = words[window_start:i]
            is_negated = any(neg in window for neg in NEGATORS)

            # Vérifier intensificateur
            intensifier = 1.0
            for j in range(max(0, i-2), i):
                if words[j] in INTENSIFIERS:
                    intensifier = INTENSIFIERS[words[j]]
                    break

            if word in POSITIVE_WORDS:
                contribution = 1.0 * intensifier
                if is_negated:
                    contribution *= -1
                    negative_count += 1
                else:
                    positive_count += 1
                score += contribution
                keywords_found.append(word)

            elif word in NEGATIVE_WORDS:
                contribution = -1.0 * intensifier
                if is_negated:
                    contribution *= -1
                    positive_count += 1
                else:
                    negative_count += 1
                score += contribution
                keywords_found.append(word)

        total = positive_count + negative_count
        if total == 0:
            return SentimentResult(0.0, "neutre", 0.0, 0, 0, 1, [])

        normalized_score = max(-1.0, min(1.0, score / max(total, 1)))
        confidence = min(1.0, total / 20)   # Plus de mots trouvés = plus de confiance

        return SentimentResult(
            score=round(normalized_score, 4),
            label="positif" if normalized_score > 0.15 else "négatif" if normalized_score < -0.15 else "neutre",
            confidence=round(confidence, 4),
            positive_count=positive_count,
            negative_count=negative_count,
            source_count=1,
            keywords_found=list(set(keywords_found))[:5],
        )

    @classmethod
    async def _collect_texts(cls, symbol: str) -> list[str]:
        """Collecte les textes depuis les sources disponibles."""
        texts = []
        search_terms = cls._get_search_terms(symbol)

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [cls._fetch_source(client, url, search_terms) for url in NEWS_SOURCES[:3]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, str) and len(r) > 50:
                    texts.append(r)

        # Ajouter textes de contexte statique par défaut si rien trouvé
        if not texts:
            texts = cls._get_context_texts(symbol)

        return texts

    @staticmethod
    async def _fetch_source(client: httpx.AsyncClient, url: str, terms: list) -> str:
        try:
            resp = await client.get(url, headers={"User-Agent": "BTF-Scanner/1.0"})
            if resp.status_code == 200:
                text = resp.text[:5000]
                return text
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_search_terms(symbol: str) -> list:
        mapping = {
            "BTC/USDT": ["bitcoin", "BTC", "crypto", "blockchain"],
            "ETH/USDT": ["ethereum", "ETH", "DeFi", "smart contract"],
            "BNB/USDT": ["Binance", "BNB", "exchange"],
            "SONATEL":  ["Sonatel", "Orange Sénégal", "télécommunications", "Dakar"],
            "CORIS BANK": ["Coris Bank", "banque", "Burkina", "finance"],
            "ECOBANK CI": ["Ecobank", "banque", "Côte d'Ivoire", "Abidjan"],
        }
        return mapping.get(symbol, [symbol])

    @staticmethod
    def _get_context_texts(symbol: str) -> list:
        """Textes de contexte par défaut – simulés pour demo."""
        contexts = {
            "BTC/USDT": [
                "Le bitcoin continue sa progression avec des achats institutionnels massifs. "
                "Les ETF Bitcoin enregistrent des afflux records cette semaine. "
                "La confiance des investisseurs est forte avec un sentiment globalement positif."
            ],
            "SONATEL": [
                "Sonatel annonce une hausse de ses bénéfices au premier trimestre. "
                "Le dividende versé aux actionnaires est en progression solide. "
                "L'expansion en Afrique de l'Ouest renforce la position dominante de l'opérateur."
            ],
        }
        return [contexts.get(symbol, "Pas de données disponibles pour ce symbole actuellement.")]


class PhysicalMarketNLP:
    """
    NLP spécialisé pour le marché physique UEMOA.
    Détecte pénuries, surplus, demandes locales.
    """

    SHORTAGE_TERMS = {
        "pénurie", "manque", "rupture", "insuffisant", "rare", "introuvable",
        "épuisé", "stock zéro", "approvisionnement difficile", "livraison bloquée",
        "frontière fermée", "route coupée", "grève", "conflit",
    }

    SURPLUS_TERMS = {
        "surplus", "abondance", "excès", "stock important", "récolte record",
        "disponible", "approvisionnement normal", "livraison assurée", "prix bas",
    }

    PRODUCT_MAPPING = {
        "poisson": ["poisson", "thon", "sardine", "tilapia", "capitaine", "congélé"],
        "céréales": ["maïs", "mil", "sorgho", "riz", "blé", "farine", "millet"],
        "légumes": ["tomate", "oignon", "gombo", "aubergine", "piment", "légume"],
        "carburant": ["essence", "gasoil", "carburant", "pétrole", "fuel", "gaz"],
        "bétail": ["bétail", "bœuf", "mouton", "chèvre", "volaille", "poulet"],
        "or": ["or", "gold", "mine", "extraction", "minerai"],
        "coton": ["coton", "fibre", "cotton", "filière"],
    }

    @classmethod
    def analyze_physical_text(cls, text: str, location: str = "") -> dict:
        text_lower = text.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))

        shortage_score = sum(1 for t in cls.SHORTAGE_TERMS if t in text_lower)
        surplus_score  = sum(1 for t in cls.SURPLUS_TERMS  if t in text_lower)

        # Identifier produits
        detected_products = []
        for category, terms in cls.PRODUCT_MAPPING.items():
            if any(term in text_lower for term in terms):
                detected_products.append(category)

        # Score de rareté 0-10
        if shortage_score > surplus_score:
            rarity = min(10, shortage_score * 2.5)
            status = "pénurie"
        elif surplus_score > shortage_score:
            rarity = max(0, 5 - surplus_score)
            status = "surplus"
        else:
            rarity = 5.0
            status = "normal"

        return {
            "rarity_score": round(rarity, 1),
            "supply_status": status,
            "detected_products": detected_products,
            "shortage_signals": shortage_score,
            "surplus_signals": surplus_score,
        }
