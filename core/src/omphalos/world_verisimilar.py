"""
Verisimilitudinous world generator for omphalOS.

This module generates synthetic but realistic trade data with:
- Plausible company names using Markov chains
- Realistic address structures by country
- Temporal patterns (seasonal flows, quarterly clustering)
- Geographic topology (realistic trade corridors)
- Statistical distributions matching real-world patterns (Zipf law for entity sizes, power law for transaction volumes)

All data is synthetic and non-identifiable. No real entities, transactions, or individuals are represented.
"""

import random, hashlib, math
from pathlib import Path
from datetime import datetime, timedelta
from .util import write_json

AOTA_DOMAINS = [
    "chemicals_precursors","machine_tools","aerospace_uas_avionics","maritime_port_equipment",
    "energy_equipment","medical_bio_lab","luxury_dual_use_consumer","services","intangibles",
    "finance_signals","procurement","research_links",
]

# Company name components for Markov chain generation
COMPANY_PREFIXES = [
    "Global", "Apex", "Precision", "Advanced", "United", "International", "Trans", "Euro", "Pacific",
    "Atlantic", "Continental", "Premier", "Elite", "Strategic", "Integrated", "Dynamic", "Quantum",
    "Sino", "Nordic", "Mediterranean", "Eastern", "Western", "Central", "Supreme", "Universal"
]

COMPANY_MIDDLES = [
    "Industrial", "Maritime", "Aerospace", "Technical", "Engineering", "Trading", "Logistics",
    "Manufacturing", "Chemical", "Bio", "Pharma", "Energy", "Power", "Medical", "Scientific",
    "Technology", "Systems", "Solutions", "Services", "Equipment", "Resources", "Materials"
]

COMPANY_SUFFIXES = [
    "Corp", "Ltd", "LLC", "Inc", "GmbH", "SA", "AG", "SpA", "BV", "Oy", "AB", "AS", "Holdings",
    "Group", "Industries", "International", "Enterprises", "Associates", "Partners"
]

# Geographic trade corridors with realistic country pairs
TRADE_CORRIDORS = [
    ("CN", "US"),  # China to United States
    ("DE", "CN"),  # Germany to China
    ("JP", "US"),  # Japan to United States
    ("CN", "IN"),  # China to India
    ("KR", "CN"),  # South Korea to China
    ("US", "MX"),  # United States to Mexico
    ("CN", "BR"),  # China to Brazil
    ("DE", "FR"),  # Germany to France
    ("GB", "DE"),  # United Kingdom to Germany
    ("CN", "AE"),  # China to United Arab Emirates (Dubai hub)
    ("SG", "CN"),  # Singapore to China (regional hub)
    ("NL", "DE"),  # Netherlands to Germany
    ("TW", "CN"),  # Taiwan to China
    ("MY", "CN"),  # Malaysia to China
    ("TH", "CN"),  # Thailand to China
]

# Street names by country theme
STREET_NAMES = {
    "US": (["Main", "Oak", "Maple", "Washington", "Park", "5th", "Market", "Industrial"], ["St", "Ave", "Blvd", "Way", "Pkwy"]),
    "CN": (["Pudong", "Zhongshan", "Nanjing", "Huangpu", "Jianguomen", "Chaoyang", "Dongfang", "Zhongguan"], ["Road", "Avenue", "Street"]),
    "DE": (["Hauptstr", "Industriestr", "Bahnhofstr", "Gartenstr", "Schulstr", "Kirchstr"], ["", "asse"]),
    "JP": (["Chuo", "Marunouchi", "Shinjuku", "Shibuya", "Minato", "Roppongi"], ["dori", "cho"]),
    "GB": (["High", "King", "Queen", "Market", "Station", "Church", "Mill"], ["Street", "Road", "Way", "Lane"]),
    "FR": (["Rue de la", "Avenue", "Boulevard", "Place"], ["République", "Commerce", "Industrie", "Paix"]),
    "KR": (["Gangnam", "Jongno", "Sejong", "Yeouido", "Itaewon"], ["ro", "gil"]),
    "BR": (["Avenida", "Rua"], ["Paulista", "Ipiranga", "das Nações", "Industrial", "do Comércio"]),
}

# Payment banks with geographic distribution
BANKS_BY_REGION = {
    "CN": ["ICBC", "Bank of China", "China Construction Bank", "Agricultural Bank"],
    "US": ["JPMorgan Chase", "Bank of America", "Citibank", "Wells Fargo"],
    "EU": ["HSBC", "BNP Paribas", "Deutsche Bank", "Santander"],
    "ME": ["Emirates NBD", "ADCB", "Mashreq Bank"],  # Middle East
    "ASIA": ["DBS Bank", "OCBC", "Standard Chartered", "Mizuho Bank"],
}

# Seasonal commodity flows (month -> domains with elevated activity)
SEASONAL_PATTERNS = {
    1: ["energy_equipment"],  # Winter energy demand
    2: ["energy_equipment"],
    3: ["chemicals_precursors"],  # Spring ag season
    4: ["machine_tools", "aerospace_uas_avionics"],  # Q1 capital spending
    9: ["chemicals_precursors"],  # Fall ag season
    10: ["machine_tools"],  # Q3 capital spending
    11: ["luxury_dual_use_consumer"],  # Holiday season
    12: ["luxury_dual_use_consumer", "energy_equipment"],
}

def _seed(profile):
    return int(hashlib.sha256(profile.encode()).hexdigest()[:8], 16)

def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        f.write(','.join(header)+'\n')
        for r in rows:
            f.write(','.join(str(x).replace(',',' ').replace('\n', ' ') for x in r)+'\n')

def _generate_company_name(rng):
    """Generate plausible company name using Markov-like combination."""
    structure = rng.choice([
        lambda: f"{rng.choice(COMPANY_PREFIXES)} {rng.choice(COMPANY_MIDDLES)} {rng.choice(COMPANY_SUFFIXES)}",
        lambda: f"{rng.choice(COMPANY_MIDDLES)} {rng.choice(COMPANY_SUFFIXES)}",
        lambda: f"{rng.choice(COMPANY_PREFIXES)} {rng.choice(COMPANY_SUFFIXES)}",
        lambda: f"{rng.choice(COMPANY_PREFIXES)}-{rng.choice(COMPANY_MIDDLES)} {rng.choice(COMPANY_SUFFIXES)}",
    ])
    return structure()

def _generate_address(rng, country):
    """Generate realistic address for given country."""
    if country not in STREET_NAMES:
        country = "US"  # Fallback

    streets, suffixes = STREET_NAMES[country]
    num = rng.randint(1, 9999)

    if country == "CN":
        return f"{num} {rng.choice(streets)} {rng.choice(suffixes)}, {rng.choice(['Shanghai', 'Beijing', 'Shenzhen', 'Guangzhou'])}"
    elif country == "DE":
        return f"{rng.choice(streets)}{rng.choice(suffixes)} {num}, {rng.choice(['Munich', 'Hamburg', 'Frankfurt', 'Berlin'])}"
    elif country == "JP":
        return f"{num}-{rng.randint(1,20)} {rng.choice(streets)}-{rng.choice(suffixes)}, {rng.choice(['Tokyo', 'Osaka', 'Nagoya'])}"
    elif country == "GB":
        return f"{num} {rng.choice(streets)} {rng.choice(suffixes)}, {rng.choice(['London', 'Manchester', 'Birmingham'])}"
    else:  # US and others
        return f"{num} {rng.choice(streets)} {rng.choice(suffixes)}, {rng.choice(['New York', 'Los Angeles', 'Chicago', 'Houston'])}"

def _get_bank_for_country(rng, country):
    """Return realistic bank name for country."""
    region_map = {
        "CN": "CN", "IN": "ASIA", "JP": "ASIA", "KR": "ASIA", "SG": "ASIA", "TH": "ASIA", "MY": "ASIA",
        "US": "US", "MX": "US",
        "DE": "EU", "FR": "EU", "GB": "EU", "NL": "EU", "IT": "EU",
        "AE": "ME", "SA": "ME",
    }
    region = region_map.get(country, "US")
    return rng.choice(BANKS_BY_REGION[region])

def _zipf_sample(rng, n, alpha=1.5):
    """Sample from Zipf distribution (power law) for realistic entity size distribution."""
    # Generate Zipf-distributed index
    # Using rejection sampling for simplicity
    while True:
        x = rng.randint(1, n)
        prob = 1.0 / (x ** alpha)
        if rng.random() < prob * (n ** alpha) / 10:  # Normalization factor (approximate)
            return x

def world_build_verisimilar(profile='national', out_dir='hydrate/world', n_entities=2000, n_shipments=5000, n_payments=4000):
    """
    Build verisimilitudinous world with realistic patterns.

    Args:
        profile: Seed profile for deterministic generation
        out_dir: Output directory
        n_entities: Number of entities to generate
        n_shipments: Number of shipments
        n_payments: Number of payments
    """
    out=Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng=random.Random(_seed(profile))

    # Meta
    meta={
        "profile":profile,
        "created_utc":datetime.utcnow().isoformat()+'Z',
        "domains":AOTA_DOMAINS,
        "recipe":{
            "entities_base":250000,
            "shipments_base":600000,
            "payments_base":500000,
            "multiplier_hint":100,
            "shards":64
        },
        "note":"Synthetic world with verisimilitudinous patterns. Non-identifiable."
    }
    write_json(out/'meta.json', meta)

    # Generate entities with realistic attributes
    entities=[]
    entity_countries = []
    for i in range(n_entities):
        # Country distribution: heavily weighted toward major trade hubs
        country_weights = {
            "CN": 0.25, "US": 0.20, "DE": 0.10, "JP": 0.08, "KR": 0.05,
            "IN": 0.05, "GB": 0.04, "FR": 0.03, "SG": 0.03, "NL": 0.02,
            "AE": 0.02, "MX": 0.02, "BR": 0.02, "TW": 0.02, "MY": 0.02,
            "TH": 0.02, "IT": 0.02, "ES": 0.01
        }
        country = rng.choices(list(country_weights.keys()), weights=list(country_weights.values()))[0]
        entity_countries.append(country)

        entity_id = f"E{i:06d}"
        entity_type = rng.choice(["firm","firm","firm","lab","broker","insurer","forwarder"])  # Weighted toward firms
        year_founded = rng.randint(1970, 2024)
        company_name = _generate_company_name(rng)
        address = _generate_address(rng, country)

        entities.append([entity_id, company_name, entity_type, year_founded, country, address])

    _write_csv(out/'shards'/'entities_000.csv',
               ["entity_id","name","entity_type","year_founded","country","address"],
               entities)

    # Generate shipments with temporal and geographic realism
    shipments=[]
    start_date = datetime(2025, 1, 1)

    for i in range(n_shipments):
        shipment_id = f"S{i:07d}"

        # Select exporter using Zipf distribution (few large exporters, many small)
        exporter_idx = _zipf_sample(rng, n_entities) - 1
        exporter_id = entities[exporter_idx][0]
        exporter_country = entity_countries[exporter_idx]

        # Select importer using trade corridors
        # If exporter is in a known trade corridor, bias toward that importer country
        importer_idx = rng.randint(0, n_entities-1)
        potential_importers = [
            (dest_country, idx)
            for (src, dest) in TRADE_CORRIDORS
            for idx, ent_country in enumerate(entity_countries)
            if src == exporter_country and dest == ent_country
        ]
        if potential_importers and rng.random() < 0.7:  # 70% chance to follow trade corridor
            _, importer_idx = rng.choice(potential_importers)
        importer_id = entities[importer_idx][0]

        # Domain selection with seasonal bias
        days_offset = rng.randint(0, 365)
        shipment_date = start_date + timedelta(days=days_offset)
        month = shipment_date.month

        if month in SEASONAL_PATTERNS and rng.random() < 0.3:  # 30% seasonal bias
            domain = rng.choice(SEASONAL_PATTERNS[month])
        else:
            domain = rng.choice(AOTA_DOMAINS[:7])  # Use primary domains

        # Incoterm and mode
        incoterm = rng.choice(["FOB", "CIF", "CIF", "DAP", "EXW", "FCA"])  # Weighted toward CIF
        mode = rng.choice(["sea", "sea", "sea", "air", "road"])  # Most trade is sea

        # Quantity and unit (power law distribution for quantity)
        qty = int(10 ** rng.uniform(0, 2.7))  # 1 to ~500 with power law
        unit = rng.choice(["kg", "kg", "pcs", "L", "MT", "units"])

        # Invoice ID (sequential with occasional gaps)
        invoice_base = 100000 + (i * 10) + rng.randint(-5, 5)
        invoice_id = f"INV{invoice_base:07d}"

        # Description
        description_templates = [
            f"{domain} item {rng.randint(100,999)}",
            f"HS{rng.randint(1000,9999)}.{rng.randint(10,99)} {domain}",
            f"{domain} component batch {rng.randint(1,99)}",
        ]
        description = rng.choice(description_templates)

        shipments.append([
            shipment_id, exporter_id, importer_id, domain, incoterm, mode,
            qty, unit, invoice_id, description, shipment_date.strftime("%Y-%m-%d")
        ])

    _write_csv(out/'shards'/'shipments_000.csv',
               ["shipment_id","exporter_id","importer_id","domain","incoterm","mode","qty","unit","invoice_id","description","date"],
               shipments)

    # Generate payments with realistic patterns
    payments=[]

    for i in range(n_payments):
        payment_id = f"P{i:07d}"

        # Select shipment
        shipment = rng.choice(shipments)
        shipment_id = shipment[0]
        exporter_id = shipment[1]
        exporter_idx = int(exporter_id[1:])
        exporter_country = entity_countries[exporter_idx]

        # Payment method distribution
        method_weights = {"wire": 0.50, "letter_of_credit": 0.30, "cashlike": 0.15, "crypto": 0.05}
        method = rng.choices(list(method_weights.keys()), weights=list(method_weights.values()))[0]

        # Amount correlated with quantity
        qty = shipment[6]
        base_amount = qty * rng.uniform(10, 500)  # Per-unit price variation
        amount = int(base_amount * rng.uniform(0.9, 1.1))  # +/- 10% noise

        # Currency
        currency_weights = {"USD": 0.60, "EUR": 0.20, "CNY": 0.10, "JPY": 0.05, "GBP": 0.05}
        ccy = rng.choices(list(currency_weights.keys()), weights=list(currency_weights.values()))[0]

        # Bank based on exporter country
        bank = _get_bank_for_country(rng, exporter_country)

        # Broker (sometimes absent)
        if rng.random() < 0.3:  # 30% use broker
            broker = f"Broker-{rng.choice(['Alpha', 'Beta', 'Gamma', 'Delta', 'Omega'])}"
        else:
            broker = ""

        payments.append([payment_id, shipment_id, method, amount, ccy, bank, broker])

    _write_csv(out/'shards'/'payments_000.csv',
               ["payment_id","shipment_id","method","amount","ccy","bank","broker"],
               payments)

    print(f"Verisimilitudinous world built: {n_entities} entities, {n_shipments} shipments, {n_payments} payments")

# Maintain backward compatibility
def world_build(profile='national', out_dir='assets/world'):
    """Legacy world builder (simple version). Use world_build_verisimilar for realistic data."""
    # Call verisimilar version with demo scale
    world_build_verisimilar(profile=profile, out_dir=out_dir, n_entities=2000, n_shipments=5000, n_payments=4000)
