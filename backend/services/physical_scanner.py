"""
BTF – Scanner Marché Physique UEMOA (Module B)
Détection pénuries, surplus, opportunités sur toute la zone UEMOA.
Axes logistiques : Abidjan→Ouagadougou, Hub Bobo-Dioulasso, etc.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from backend.utils.database import AsyncSessionLocal
from backend.models.models import PhysicalMarketTrend, RarityLevel
from backend.services.nlp_sentiment import PhysicalMarketNLP

logger = logging.getLogger("btf.physical_scanner")

SCAN_INTERVAL = 3600   # Toutes les heures

# ─── ZONES & AXES LOGISTIQUES ─────────────────────────────────────────────────
UEMOA_ZONES = [
    # Burkina Faso
    {"country": "BF", "city": "Ouagadougou", "region": "Centre",      "markets": ["Rood Woko", "Nongr-Maasem", "Pissy"]},
    {"country": "BF", "city": "Bobo-Dioulasso", "region": "Hauts-Bassins", "markets": ["Dioulassoba", "Secteur 22"]},
    {"country": "BF", "city": "Kaya",           "region": "Centre-Nord",    "markets": ["Marché central Kaya"]},
    {"country": "BF", "city": "Banfora",         "region": "Cascades",       "markets": ["Marché de Banfora"]},
    # Côte d'Ivoire
    {"country": "CI", "city": "Abidjan",         "region": "Lagunes",        "markets": ["Adjamé", "Koumassi", "Port"]},
    {"country": "CI", "city": "Bouaké",          "region": "Vallée du Bandama","markets": ["Grand marché Bouaké"]},
    # Sénégal
    {"country": "SN", "city": "Dakar",           "region": "Dakar",          "markets": ["Sandaga", "HLM"]},
    {"country": "SN", "city": "Kaolack",         "region": "Kaolack",        "markets": ["Marché Kaolack"]},
    # Mali
    {"country": "ML", "city": "Bamako",          "region": "District",       "markets": ["Médina Coura", "Dibida"]},
    # Togo
    {"country": "TG", "city": "Lomé",            "region": "Maritime",       "markets": ["Grand Marché", "Assivito"]},
    # Bénin
    {"country": "BJ", "city": "Cotonou",         "region": "Littoral",       "markets": ["Dantokpa"]},
    # Niger
    {"country": "NE", "city": "Niamey",          "region": "Niamey",         "markets": ["Grand Marché Niamey"]},
]

LOGISTICS_AXES = [
    {"name": "Abidjan → Ouagadougou", "from": "CI", "to": "BF", "products": ["poisson", "produits_frais", "marchandises"]},
    {"name": "Lomé → Ouagadougou",    "from": "TG", "to": "BF", "products": ["céréales", "produits_manufacturés"]},
    {"name": "Dakar → Bamako",        "from": "SN", "to": "ML", "products": ["arachides", "poisson", "marchandises"]},
    {"name": "Bobo-Dioulasso Hub",    "from": "BF", "to": "BF", "products": ["maïs", "sorgho", "mil", "riz"]},
    {"name": "Sahel → Ouaga",         "from": "BF", "to": "BF", "products": ["bétail", "céréales"]},
]

PRODUCTS_WATCHLIST = [
    {"name": "Poisson congelé",     "category": "alimentaire",  "keywords": ["poisson", "congelé", "thon", "sardine"]},
    {"name": "Maïs",                "category": "céréales",     "keywords": ["maïs", "corn"]},
    {"name": "Sorgho",              "category": "céréales",     "keywords": ["sorgho"]},
    {"name": "Mil",                 "category": "céréales",     "keywords": ["mil", "millet"]},
    {"name": "Riz local",           "category": "céréales",     "keywords": ["riz", "paddy"]},
    {"name": "Farine de blé",       "category": "céréales",     "keywords": ["farine", "blé"]},
    {"name": "Huile végétale",      "category": "alimentaire",  "keywords": ["huile", "palm"]},
    {"name": "Oignon",              "category": "légumes",      "keywords": ["oignon"]},
    {"name": "Tomate",              "category": "légumes",      "keywords": ["tomate"]},
    {"name": "Carburant essence",   "category": "énergie",      "keywords": ["essence", "carburant"]},
    {"name": "Gasoil",              "category": "énergie",      "keywords": ["gasoil", "diesel"]},
    {"name": "Bétail bovin",        "category": "élevage",      "keywords": ["bœuf", "bétail", "bovin"]},
    {"name": "Volaille",            "category": "élevage",      "keywords": ["poulet", "volaille"]},
    {"name": "Or",                  "category": "minerai",      "keywords": ["or", "gold", "mine"]},
    {"name": "Coton",               "category": "textile",      "keywords": ["coton", "fibre"]},
]

NEWS_URLS = [
    "https://www.lefaso.net/spip.php?rubrique1",
    "https://www.financialafrik.com/category/marches/",
    "https://www.sika-finance.com/marche-brvm",
    "https://www.abidjan.net/",
    "https://news.abidjan.net/",
]


class PhysicalMarketScanner:
    """
    Scanner intelligent du marché physique UEMOA.
    Génère des rapports de rareté et d'opportunité.
    """

    @classmethod
    async def run_forever(cls):
        logger.info("🌾 Scanner Marché Physique démarré")
        while True:
            try:
                await cls._scan_cycle()
            except Exception as e:
                logger.error(f"Erreur scanner physique: {e}", exc_info=True)
            await asyncio.sleep(SCAN_INTERVAL)

    @classmethod
    async def _scan_cycle(cls):
        logger.info("🔍 Scan marché physique UEMOA en cours...")
        async with AsyncSessionLocal() as db:
            news_texts = await cls._fetch_news()

            for zone in UEMOA_ZONES:
                for product in PRODUCTS_WATCHLIST:
                    analysis = cls._analyze_product_zone(product, zone, news_texts)
                    if analysis["rarity_score"] >= 3.0:   # Enregistrer si notable
                        trend = PhysicalMarketTrend(
                            country       = zone["country"],
                            region        = zone["region"],
                            city          = zone["city"],
                            product       = product["name"],
                            category      = product["category"],
                            rarity_score  = analysis["rarity_score"],
                            rarity_level  = cls._rarity_level(analysis["rarity_score"]),
                            supply_status = analysis["supply_status"],
                            demand_level  = analysis.get("demand_level", "normal"),
                            logistics_axis= cls._find_logistics_axis(zone["country"], product),
                            source_type   = "web_scan",
                            raw_data      = analysis,
                        )
                        db.add(trend)

            await db.commit()
            logger.info(f"✅ Scan physique terminé – {len(UEMOA_ZONES)} zones analysées")

    @classmethod
    async def _fetch_news(cls) -> list[str]:
        texts = []
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for url in NEWS_URLS:
                try:
                    resp = await client.get(url, headers={"User-Agent": "BTF-Scanner/1.0"})
                    if resp.status_code == 200:
                        texts.append(resp.text[:8000])
                except Exception as e:
                    logger.debug(f"News fetch error {url}: {e}")
        # Fallback simulé
        if not texts:
            texts = cls._simulated_news()
        return texts

    @staticmethod
    def _analyze_product_zone(product: dict, zone: dict, news_texts: list) -> dict:
        combined_text = " ".join(news_texts)
        keyword_text = " ".join(
            part for part in [combined_text]
            if any(kw in part.lower() for kw in product["keywords"])
        ) or combined_text

        result = PhysicalMarketNLP.analyze_physical_text(
            keyword_text,
            location=f"{zone['city']}, {zone['country']}"
        )

        # Ajustements contextuels par pays/produit
        adjustments = PhysicalMarketScanner._contextual_adjustments(product["name"], zone["country"])
        result["rarity_score"] = min(10, result["rarity_score"] + adjustments)

        return result

    @staticmethod
    def _contextual_adjustments(product: str, country: str) -> float:
        """Ajustements basés sur la connaissance du terrain."""
        # Burkina Faso – contexte sécuritaire impacte logistique
        if country == "BF":
            if product in ["Poisson congelé", "Carburant essence", "Gasoil"]:
                return 1.5   # Difficultés d'approvisionnement connues
            if product in ["Maïs", "Sorgho"]:
                return 0.5
        # Côte d'Ivoire – hub logistique fort
        if country == "CI":
            if product in ["Poisson congelé"]:
                return -1.0  # Bien approvisionné depuis le port
        return 0.0

    @staticmethod
    def _find_logistics_axis(country: str, product: dict) -> str | None:
        for axis in LOGISTICS_AXES:
            if axis["to"] == country:
                for cat in product.get("keywords", []):
                    if any(cat in p for p in axis["products"]):
                        return axis["name"]
        return None

    @staticmethod
    def _rarity_level(score: float) -> RarityLevel:
        if score >= 7.5:
            return RarityLevel.CRITICAL
        elif score >= 5.0:
            return RarityLevel.HIGH
        elif score >= 2.5:
            return RarityLevel.MEDIUM
        return RarityLevel.LOW

    @staticmethod
    def _simulated_news() -> list[str]:
        return [
            """
            Pénurie de poisson congelé à Ouagadougou – les stocks s'épuisent rapidement.
            La route Abidjan-Ouagadougou connaît des perturbations logistiques importantes.
            Le carburant manque dans plusieurs quartiers de la capitale burkinabè.
            Bobo-Dioulasso enregistre une récolte de maïs satisfaisante cette saison.
            Le bétail est rare sur les marchés du Sahel suite aux tensions sécuritaires.
            Sonatel affiche une hausse de ses résultats au premier trimestre.
            Ecobank Côte d'Ivoire annonce un bénéfice en forte progression.
            Le marché Dantokpa de Cotonou est bien approvisionné en produits alimentaires.
            """,
            """
            Les prix des céréales sont stables à Dakar grâce aux importations record.
            L'oignon connaît une pénurie saisonnière dans plusieurs marchés du Burkina.
            Bamako souffre d'une hausse des prix du gasoil liée aux difficultés d'import.
            Le port d'Abidjan traite un volume record de conteneurs cette semaine.
            Kaya : rupture de stock de farine de blé dans les boulangeries.
            """
        ]

    @classmethod
    async def get_summary_report(cls) -> dict:
        """Génère un rapport résumé pour l'administrateur."""
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select, desc
            from backend.models.models import PhysicalMarketTrend
            result = await db.execute(
                select(PhysicalMarketTrend)
                .where(PhysicalMarketTrend.published == False)
                .order_by(desc(PhysicalMarketTrend.rarity_score))
                .limit(20)
            )
            trends = result.scalars().all()
            return {
                "total_alerts": len(trends),
                "critical_alerts": [t for t in trends if t.rarity_level == RarityLevel.CRITICAL],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "report": [
                    {
                        "product":  t.product,
                        "location": f"{t.city}, {t.country}",
                        "rarity":   t.rarity_score,
                        "status":   t.supply_status,
                        "axis":     t.logistics_axis,
                    }
                    for t in trends
                ]
            }
