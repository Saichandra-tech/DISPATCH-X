"""
DispatchX AI Fraud Detection & Risk Scoring Engine
====================================================
Pure Python module — no ML framework required.
Formula:
    RiskScore = 0.30*SpeedScore + 0.30*(1-BehaviorScore) + 0.20*NetworkRisk + 0.20*GraphScore

Fraud signals:
  A) GPS Analysis   — teleportation, overspeed, static spoofing
  B) Behavioral     — delivery frequency, route consistency, activity patterns
  C) Network        — shared IP clusters, shared device fingerprints
  D) Graph          — fraud ring detection via connection graph
"""

import math
import hashlib
from datetime import timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
MAX_LEGAL_SPEED_KMH    = 100.0   # above this = anomaly
TELEPORT_DISTANCE_KM   = 20.0   # jump >20km in <5min = teleportation
STATIC_SPOOF_THRESHOLD = 0.05   # std deviation in km below this = static spoof
FRAUD_RING_MIN_SHARED  = 2      # min shared connections to flag ring
AQI_TRIGGER_THRESHOLD  = 300
RAIN_TRIGGER_MM        = 50.0
WEIGHTS = {'speed': 0.30, 'behavior': 0.30, 'network': 0.20, 'graph': 0.20}


# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────
@dataclass
class GPSPoint:
    lat: float
    lon: float
    timestamp: object      # datetime
    speed_kmh: float = 0.0


@dataclass
class FraudSignal:
    signal_type: str       # gps_teleport | overspeed | static_spoof | shared_ip | shared_device | ring
    severity: str          # low | medium | high | critical
    description: str
    evidence: dict = field(default_factory=dict)


@dataclass
class RiskAssessment:
    partner_id: int
    risk_score: float          # 0.0 – 1.0
    risk_level: str            # low | medium | high | critical
    decision: str              # ALLOW | MONITOR | OTP_VERIFY | BLOCK
    component_scores: dict
    fraud_signals: List[FraudSignal]
    payout_eligible: bool
    delay_reason: Optional[str] = None


# ─────────────────────────────────────────────
# A. GPS ANALYSIS
# ─────────────────────────────────────────────
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda= math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def analyze_gps_track(points: List[GPSPoint]) -> Tuple[float, List[FraudSignal]]:
    """
    Analyze a GPS track for fraud signals.
    Returns (anomaly_score 0-1, list_of_signals)
    """
    if len(points) < 2:
        return 0.0, []

    signals: List[FraudSignal] = []
    anomaly_count = 0
    max_speed = 0.0

    for i in range(1, len(points)):
        prev, curr = points[i-1], points[i]

        # Time delta
        dt = (curr.timestamp - prev.timestamp).total_seconds()
        if dt <= 0:
            continue
        dt_minutes = dt / 60.0

        # Distance
        dist_km = haversine_km(prev.lat, prev.lon, curr.lat, curr.lon)

        # Speed check
        speed = (dist_km / (dt / 3600.0)) if dt > 0 else 0
        max_speed = max(max_speed, speed)

        if speed > MAX_LEGAL_SPEED_KMH:
            severity = 'critical' if speed > 150 else 'high'
            signals.append(FraudSignal(
                signal_type='overspeed',
                severity=severity,
                description=f"Speed {speed:.1f} km/h detected between points",
                evidence={'speed_kmh': round(speed, 1), 'distance_km': round(dist_km, 2)}
            ))
            anomaly_count += 1

        # Teleportation check
        if dist_km > TELEPORT_DISTANCE_KM and dt_minutes < 5:
            signals.append(FraudSignal(
                signal_type='gps_teleport',
                severity='critical',
                description=f"Teleportation: {dist_km:.1f}km in {dt_minutes:.1f} minutes",
                evidence={'distance_km': round(dist_km, 2), 'minutes': round(dt_minutes, 1)}
            ))
            anomaly_count += 2

    # Static spoofing: all points nearly identical
    if len(points) >= 5:
        lats = [p.lat for p in points]
        lons = [p.lon for p in points]
        lat_std = _std_dev(lats)
        lon_std = _std_dev(lons)
        if lat_std < STATIC_SPOOF_THRESHOLD and lon_std < STATIC_SPOOF_THRESHOLD:
            signals.append(FraudSignal(
                signal_type='static_spoof',
                severity='high',
                description="GPS points suspiciously static — possible location spoofing",
                evidence={'lat_std': round(lat_std, 5), 'lon_std': round(lon_std, 5)}
            ))
            anomaly_count += 2

    # Score: fraction of anomalous transitions
    total_transitions = len(points) - 1
    score = min(anomaly_count / max(total_transitions, 1), 1.0)
    return score, signals


def _std_dev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


# ─────────────────────────────────────────────
# B. BEHAVIORAL ANALYSIS
# ─────────────────────────────────────────────
def analyze_behavior(
    deliveries_per_day: int,
    avg_active_hours: float,
    route_variance: float,      # 0-1: how varied are routes (low = suspicious)
    claim_frequency: int,       # claims per month
    days_active: int,
) -> Tuple[float, List[FraudSignal]]:
    """
    Returns (behavior_score 0-1, signals)
    Higher score = more trustworthy behavior
    """
    signals: List[FraudSignal] = []
    score = 1.0

    # Unrealistically high deliveries
    if deliveries_per_day > 20:
        penalty = min((deliveries_per_day - 20) / 20.0, 0.4)
        score -= penalty
        signals.append(FraudSignal(
            'overspeed', 'medium',
            f"{deliveries_per_day} deliveries/day exceeds realistic maximum",
            {'deliveries': deliveries_per_day}
        ))

    # Active hours > 18/day is suspicious
    if avg_active_hours > 18:
        score -= 0.3
        signals.append(FraudSignal(
            'static_spoof', 'high',
            f"Active {avg_active_hours:.1f} hrs/day — continuous activity flag",
            {'hours': avg_active_hours}
        ))

    # Extremely repetitive routes (low variance)
    if route_variance < 0.1:
        score -= 0.25
        signals.append(FraudSignal(
            'static_spoof', 'medium',
            "Route variance critically low — robotic delivery pattern detected",
            {'variance': route_variance}
        ))

    # High claim frequency relative to active days
    if days_active > 0:
        claim_rate = claim_frequency / max(days_active / 30.0, 1)
        if claim_rate > 4:
            score -= 0.2
            signals.append(FraudSignal(
                'ring', 'medium',
                f"Claim rate {claim_rate:.1f}x/month exceeds average",
                {'rate': round(claim_rate, 2)}
            ))

    return max(0.0, min(1.0, score)), signals


# ─────────────────────────────────────────────
# C. NETWORK / DEVICE ANALYSIS
# ─────────────────────────────────────────────
def analyze_network(
    ip_address: str,
    device_id: str,
    all_partners: List[Dict]   # list of {id, ip, device_id}
) -> Tuple[float, List[FraudSignal]]:
    """
    Returns (network_risk_score 0-1, signals)
    Checks for shared IP and shared device across accounts
    """
    signals: List[FraudSignal] = []
    risk = 0.0

    ip_peers    = [p for p in all_partners if p.get('ip') == ip_address]
    device_peers= [p for p in all_partners if p.get('device_id') == device_id and p.get('device_id')]

    if len(ip_peers) >= FRAUD_RING_MIN_SHARED:
        severity = 'critical' if len(ip_peers) >= 5 else 'high'
        risk += min(len(ip_peers) * 0.15, 0.6)
        signals.append(FraudSignal(
            signal_type='shared_ip',
            severity=severity,
            description=f"IP {ip_address} shared across {len(ip_peers)} accounts",
            evidence={'peer_ids': [p['id'] for p in ip_peers], 'count': len(ip_peers)}
        ))

    if len(device_peers) >= 2:
        risk += min(len(device_peers) * 0.20, 0.6)
        signals.append(FraudSignal(
            signal_type='shared_device',
            severity='critical',
            description=f"Device {device_id} used by {len(device_peers)} accounts",
            evidence={'peer_ids': [p['id'] for p in device_peers], 'count': len(device_peers)}
        ))

    return min(risk, 1.0), signals


# ─────────────────────────────────────────────
# D. GRAPH-BASED FRAUD RING DETECTION
# ─────────────────────────────────────────────
class FraudGraph:
    """
    Build a graph where nodes = partners and edges = shared attributes.
    Detect connected clusters (fraud rings).
    """
    def __init__(self):
        self.adjacency: Dict[int, set] = {}
        self.edge_types: Dict[Tuple, List[str]] = {}

    def add_edge(self, id_a: int, id_b: int, edge_type: str):
        if id_a not in self.adjacency:
            self.adjacency[id_a] = set()
        if id_b not in self.adjacency:
            self.adjacency[id_b] = set()
        self.adjacency[id_a].add(id_b)
        self.adjacency[id_b].add(id_a)
        key = (min(id_a, id_b), max(id_a, id_b))
        if key not in self.edge_types:
            self.edge_types[key] = []
        self.edge_types[key].append(edge_type)

    def build_from_partners(self, partners: List[Dict]):
        """Build graph from list of partner dicts with ip, device_id, zone fields."""
        # Group by shared IP
        ip_groups: Dict[str, List] = {}
        for p in partners:
            ip = p.get('ip_address', '')
            if ip:
                ip_groups.setdefault(ip, []).append(p['id'])

        # Group by shared device
        dev_groups: Dict[str, List] = {}
        for p in partners:
            dev = p.get('device_id', '')
            if dev:
                dev_groups.setdefault(dev, []).append(p['id'])

        for group in ip_groups.values():
            if len(group) > 1:
                for i in range(len(group)):
                    for j in range(i+1, len(group)):
                        self.add_edge(group[i], group[j], 'shared_ip')

        for group in dev_groups.values():
            if len(group) > 1:
                for i in range(len(group)):
                    for j in range(i+1, len(group)):
                        self.add_edge(group[i], group[j], 'shared_device')

    def get_clusters(self, min_size: int = 2) -> List[List[int]]:
        """Find connected components (fraud rings) with BFS."""
        visited = set()
        clusters = []
        for node in self.adjacency:
            if node not in visited:
                cluster = []
                queue = [node]
                while queue:
                    curr = queue.pop(0)
                    if curr in visited:
                        continue
                    visited.add(curr)
                    cluster.append(curr)
                    queue.extend(self.adjacency.get(curr, set()) - visited)
                if len(cluster) >= min_size:
                    clusters.append(cluster)
        return clusters

    def graph_risk_score(self, partner_id: int) -> float:
        """Score 0-1 based on how connected this partner is to fraud clusters."""
        connections = len(self.adjacency.get(partner_id, set()))
        clusters = self.get_clusters()
        in_cluster = any(partner_id in c for c in clusters)
        if in_cluster:
            cluster_size = next((len(c) for c in clusters if partner_id in c), 1)
            return min(0.3 + connections * 0.1 + cluster_size * 0.05, 1.0)
        return min(connections * 0.05, 0.3)


# ─────────────────────────────────────────────
# MASTER RISK ASSESSMENT
# ─────────────────────────────────────────────
def assess_risk(
    partner_id: int,
    gps_points: List[GPSPoint],
    deliveries_per_day: int,
    avg_active_hours: float,
    route_variance: float,
    claim_frequency: int,
    days_active: int,
    ip_address: str,
    device_id: str,
    all_partners: List[Dict],
    fraud_graph: Optional[FraudGraph] = None,
) -> RiskAssessment:
    """
    Master function. Runs all four detectors and combines into a final risk score.
    """
    all_signals: List[FraudSignal] = []

    # A. GPS Score
    gps_score, gps_signals = analyze_gps_track(gps_points)
    all_signals.extend(gps_signals)

    # B. Behavior Score (inverted — high score = more trustworthy)
    behavior_trust, beh_signals = analyze_behavior(
        deliveries_per_day, avg_active_hours,
        route_variance, claim_frequency, days_active
    )
    all_signals.extend(beh_signals)

    # C. Network Risk
    network_risk, net_signals = analyze_network(ip_address, device_id, all_partners)
    all_signals.extend(net_signals)

    # D. Graph Risk
    graph_score = fraud_graph.graph_risk_score(partner_id) if fraud_graph else 0.0
    if graph_score > 0.4:
        all_signals.append(FraudSignal(
            'ring', 'high' if graph_score > 0.6 else 'medium',
            f"Partner is part of a fraud cluster (graph score {graph_score:.2f})",
            {'graph_score': round(graph_score, 3)}
        ))

    # Composite Score
    speed_score  = max(gps_score, 0.0)
    behavior_risk = 1.0 - behavior_trust

    composite = (
        WEIGHTS['speed']    * speed_score    +
        WEIGHTS['behavior'] * behavior_risk  +
        WEIGHTS['network']  * network_risk   +
        WEIGHTS['graph']    * graph_score
    )
    composite = round(min(composite, 1.0), 3)

    # Classify
    if composite < 0.35:
        level, decision, eligible = 'low',      'ALLOW',      True
    elif composite < 0.55:
        level, decision, eligible = 'medium',   'MONITOR',    True
    elif composite < 0.75:
        level, decision, eligible = 'high',     'OTP_VERIFY', True
    else:
        level, decision, eligible = 'critical', 'BLOCK',      False

    delay_reason = None
    if not eligible:
        delay_reason = "Payout blocked: critical fraud risk detected"
    elif decision == 'OTP_VERIFY':
        delay_reason = "Payout delayed pending OTP verification"

    return RiskAssessment(
        partner_id       = partner_id,
        risk_score       = composite,
        risk_level       = level,
        decision         = decision,
        component_scores = {
            'gps_score':    round(gps_score, 3),
            'behavior_risk':round(behavior_risk, 3),
            'network_risk': round(network_risk, 3),
            'graph_score':  round(graph_score, 3),
            'composite':    composite,
        },
        fraud_signals    = all_signals,
        payout_eligible  = eligible,
        delay_reason     = delay_reason,
    )


# ─────────────────────────────────────────────
# PARAMETRIC TRIGGER EVALUATOR
# ─────────────────────────────────────────────
def evaluate_parametric_trigger(event_type: str, value: float, plan_covers: dict) -> dict:
    """
    Determine if a parametric event should trigger a payout.
    Returns {triggered: bool, reason: str, multiplier: float}
    """
    triggers = {
        'rain':    {'threshold': RAIN_TRIGGER_MM,  'plan_key': 'covers_rain'},
        'aqi':     {'threshold': AQI_TRIGGER_THRESHOLD, 'plan_key': 'covers_aqi'},
        'curfew':  {'threshold': 1.0,              'plan_key': 'covers_curfew'},
        'cyclone': {'threshold': 1.0,              'plan_key': 'covers_cyclone'},
        'flood':   {'threshold': 1.0,              'plan_key': 'covers_rain'},
    }
    config = triggers.get(event_type)
    if not config:
        return {'triggered': False, 'reason': 'Unknown event type', 'multiplier': 0}

    if not plan_covers.get(config['plan_key'], False):
        return {'triggered': False, 'reason': f'Plan does not cover {event_type}', 'multiplier': 0}

    if value < config['threshold']:
        return {
            'triggered': False,
            'reason': f"Value {value} below threshold {config['threshold']}",
            'multiplier': 0
        }

    # Severity multiplier
    if event_type == 'rain':
        multiplier = min(value / RAIN_TRIGGER_MM, 2.0)
    elif event_type == 'aqi':
        multiplier = min(value / AQI_TRIGGER_THRESHOLD, 2.0)
    else:
        multiplier = 1.0

    return {
        'triggered': True,
        'reason': f"{event_type.upper()} threshold exceeded: {value} >= {config['threshold']}",
        'multiplier': round(multiplier, 2),
    }


# ─────────────────────────────────────────────
# PAYOUT DECISION ENGINE
# ─────────────────────────────────────────────
def decide_payout(
    risk_assessment: RiskAssessment,
    parametric_result: dict,
    daily_coverage: float,
) -> dict:
    """
    Final payout decision combining parametric trigger + fraud check.
    Returns {status, amount, reason}
    """
    if not parametric_result.get('triggered', False):
        return {'status': 'no_trigger', 'amount': 0, 'reason': parametric_result.get('reason', 'Not triggered')}

    base_amount = daily_coverage * parametric_result['multiplier']

    if risk_assessment.decision == 'BLOCK':
        return {
            'status':  'blocked',
            'amount':  0,
            'reason':  risk_assessment.delay_reason or 'Critical fraud risk',
        }
    elif risk_assessment.decision == 'OTP_VERIFY':
        return {
            'status':  'delayed',
            'amount':  round(base_amount, 2),
            'reason':  'OTP verification required before release',
        }
    elif risk_assessment.decision == 'MONITOR':
        return {
            'status':  'released',
            'amount':  round(base_amount, 2),
            'reason':  'Released — account under monitoring',
        }
    else:
        return {
            'status':  'released',
            'amount':  round(base_amount, 2),
            'reason':  'Auto-released: all checks passed',
        }
