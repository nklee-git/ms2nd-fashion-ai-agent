"""
NQNQ 가상데이터 생성 스크립트 v2
근거 문서: 00. Home / 01. Master Roadmap (Year1-3) — 2026.08 개정판 (카카오 생태계 반영, Y3 1,000억 목표)
           30. Supply Chain & Inventory / 33. Returns & RMA Process — 채널별 반품 처리 차별화

v1 대비 변경점:
  1. 연매출 목표를 Y1 100억 / Y2 400억(+300%) / Y3 1,000억(+150%)으로 상향
  2. 10개 분기로 나눠 분기별 매출 타겟을 먼저 정하고, 그 타겟에 맞춰 일별 주문수를
     multinomial 분포로 역산 (기존 Poisson 휴리스틱보다 목표 정확도 높음)
  3. 주문량이 급증(연 최대 170만 건)하므로 SQLAlchemy ORM 대신 sqlite3 executemany
     벌크 insert로 재작성 (성능)
  4. 온라인/오프라인 채널별 반품 처리 방식 차별화 (33번 문서 2026.08 개정 반영)
  5. 쇼룸 오픈 전 사전 재고 비축 이벤트 추가

⚠️ 단순화 가정:
  - STAFF/TASK 등 조직 운영 데이터는 이번 라운드에서 다루지 않음 (71번 문서 백로그 유지)
  - AOV는 분기별 활성 카테고리 평균가 × 평균 아이템수(1.5)로 근사 추정 → 실제 매출은
    타겟과 정확히 일치하지 않을 수 있음 (실행 후 결과 요약에서 비교)
"""

import random
import sqlite3
from datetime import date, datetime, timedelta
from itertools import count as _count

import numpy as np

from models import get_engine, init_db

random.seed(42)
np.random.seed(42)

TODAY = date(2026, 8, 9)
LAUNCH_DATE = date(2024, 3, 1)
DB_PATH = "nqnq.db"

# ---------------------------------------------------------------------------
# 마스터 데이터 정의
# ---------------------------------------------------------------------------
CATEGORIES = {
    "TOP": {"name": "상의", "intro": date(2024, 3, 1), "body_codes": ["STR", "WAV", "NAT"],
            "sizes": ["S", "M", "L"], "colors": ["BLK", "WHT"], "price": 39000, "return_rate": 0.15},
    "PNT": {"name": "하의", "intro": date(2024, 3, 1), "body_codes": ["5LT", "PLT"],
            "sizes": ["XS", "S", "M", "L", "XL"], "colors": ["BLK", "GRY", "BEG"], "price": 49000, "return_rate": 0.20},
    "CLR": {"name": "컬러베이직", "intro": date(2024, 3, 1), "body_codes": ["WRM", "COOL", "MUT"],
            "sizes": ["S", "M", "L"], "colors": ["CRM", "ASH", "IVR"], "price": 35000, "return_rate": 0.10},
    "OUT": {"name": "아우터", "intro": date(2025, 3, 1), "body_codes": ["STR", "WAV", "NAT"],
            "sizes": ["S", "M", "L"], "colors": ["BLK", "BEG", "GRY", "NVY"], "price": 89000, "return_rate": 0.18},
    "ACC": {"name": "액세서리", "intro": date(2026, 3, 1), "body_codes": ["BAG", "BLT", "SCF"],
            "sizes": ["FREE"], "colors": ["BLK", "BEG", "WHT", "BRN"], "price": 19000, "return_rate": 0.08},
    "DRS": {"name": "원피스", "intro": date(2026, 3, 1), "body_codes": ["STR", "WAV", "NAT"],
            "sizes": ["S", "M", "L"], "colors": ["BLK", "IVR"], "price": 59000, "return_rate": 0.15},
}

COST_RATIO = 0.48
LEAD_TIME_DAYS = 52
AVG_ITEMS_PER_ORDER = 1.5  # weights=[0.6,0.3,0.1] for 1,2,3개 -> 기댓값 1.5

# --- 동적 재고정책 (2026.08 개정: 매출 목표가 기존 대비 대폭 상향되면서
#     고정 수치(SKU당 200장/파레벨 150장)로는 병목 발생 -> 32.Inventory Policy 문서의
#     "실판매 데이터 기반 재계산" 원칙을 실제로 적용. 분기별 SKU당 평균 판매속도 x
#     리드타임 기반으로 재주문점/파레벨을 동적으로 산출한다. ---
REORDER_BUFFER = 1.3   # 리드타임 대비 재주문점 버퍼
PAR_BUFFER = 3.0        # 리드타임 대비 파레벨 버퍼 (성장 가속 구간 대응)
INITIAL_BUFFER = 3.0    # 출시 시점 초도 물량 버퍼
SAFETY_STOCK_RATIO = 0.5  # 재주문점 대비 안전재고 비율

PROMO_WINDOWS = [
    ((3, 1), (3, 14), 2.5, "신학기 프로모션"),
    ((7, 25), (8, 10), 2.5, "여름 정리 세일"),
    ((11, 20), (11, 30), 3.0, "블랙프라이데이"),
    ((12, 15), (1, 15), 2.0, "연말 이월 프로모션"),
]

# 01. Master Roadmap (2026.08 개정) 분기별 매출 타겟 (전체 분기 기준, 부분 분기는 코드에서 일할 계산)
QUARTERS = [
    (date(2024, 3, 1), date(2024, 5, 31), 2_000_000_000),
    (date(2024, 6, 1), date(2024, 8, 31), 2_200_000_000),
    (date(2024, 9, 1), date(2024, 11, 30), 2_800_000_000),
    (date(2024, 12, 1), date(2025, 2, 28), 3_000_000_000),
    (date(2025, 3, 1), date(2025, 5, 31), 8_000_000_000),
    (date(2025, 6, 1), date(2025, 8, 31), 8_800_000_000),
    (date(2025, 9, 1), date(2025, 11, 30), 11_200_000_000),
    (date(2025, 12, 1), date(2026, 2, 28), 12_000_000_000),
    (date(2026, 3, 1), date(2026, 5, 31), 20_000_000_000),
    (date(2026, 6, 1), date(2026, 8, 31), 22_000_000_000),
]

STORES = {
    "STORE-01": {"type": "팝업", "location": "성수", "open": date(2024, 10, 1), "close": date(2024, 10, 31)},
    "STORE-02": {"type": "상설쇼룸", "location": "홍대", "open": date(2025, 3, 15), "close": None},
    "STORE-03": {"type": "팝업", "location": "강남", "open": date(2025, 11, 1), "close": date(2025, 11, 30)},
    "STORE-04": {"type": "상설쇼룸", "location": "강남", "open": date(2026, 4, 1), "close": None},
}
SHOWROOM_PREP_WEEKS = 4  # 쇼룸(상설) 오픈 전 사전 재고 비축 기간

# --- 서울 월평균기온 (기상청 기후평년값 1991~2020, data.kma.go.kr) ---
# 실시간 API는 서비스키 인증이 필요해(네트워크 제약으로 이번 라운드는 미연동) 공식 평년값으로 근사.
SEOUL_MONTHLY_TEMP = {
    1: -2.0, 2: 0.4, 3: 5.7, 4: 12.5, 5: 17.8, 6: 22.2,
    7: 24.9, 8: 26.1, 9: 21.3, 10: 14.6, 11: 7.5, 12: 0.4,
}

# 24절기 날짜(양력, 매년 거의 고정) — 월평균기온을 절기 단위로 보간해 문서화용으로 제공.
# 실제 수요 가중치 계산은 get_temp()의 일 단위 보간을 사용(절기보다 촘촘함).
SOLAR_TERMS_24 = [
    ("입춘", 2, 4), ("우수", 2, 19), ("경칩", 3, 6), ("춘분", 3, 21),
    ("청명", 4, 5), ("곡우", 4, 20), ("입하", 5, 6), ("소만", 5, 21),
    ("망종", 6, 6), ("하지", 6, 21), ("소서", 7, 7), ("대서", 7, 23),
    ("입추", 8, 8), ("처서", 8, 23), ("백로", 9, 8), ("추분", 9, 23),
    ("한로", 10, 8), ("상강", 10, 23), ("입동", 11, 7), ("소설", 11, 22),
    ("대설", 12, 7), ("동지", 12, 22), ("소한", 1, 6), ("대한", 1, 20),
]


def get_temp(d: date) -> float:
    """월평균기온을 각 월 15일 기준으로 두고 인접 월 사이를 선형보간 -> 일 단위 근사 기온."""
    m, day = d.month, d.day
    if day >= 15:
        m1, m2, frac = m, (m % 12) + 1, (day - 15) / 30
    else:
        m1, m2, frac = (m - 2) % 12 + 1, m, (day + 15) / 30
    t1, t2 = SEOUL_MONTHLY_TEMP[m1], SEOUL_MONTHLY_TEMP[m2]
    return t1 + (t2 - t1) * frac


# 카테고리별 기온 민감도 (계수는 설계값, 기준 기온은 실측 평년값)
def category_weather_factor(cat_code: str, temp: float) -> float:
    if cat_code == "OUT":
        return 1.0 + max(0.0, (18 - temp) / 18) * 1.5       # 추울수록 아우터 수요↑
    if cat_code == "DRS":
        return 1.0 + max(0.0, (temp - 15) / 15) * 1.2       # 따뜻할수록 원피스 수요↑
    if cat_code == "TOP":
        return 1.0 + max(0.0, (temp - 10) / 25) * 0.4       # 완만하게 따뜻할수록↑
    if cat_code == "PNT":
        return 1.0 + max(0.0, (15 - temp) / 25) * 0.5       # 완만하게 추울수록↑
    return 1.0  # CLR, ACC는 계절 둔감(이너/소품)


# --- 20대 여성 신장 분포 실측치 (2018 디지틀조선 설문 기반 응답 비율, 사이즈코리아 7차 조사와 정합) ---
# 155cm미만 7% / 156~160cm 29% / 161~165cm 37% / 166~170cm 23% / 170cm이상 4%
SIZE_WEIGHTS_5 = {"XS": 0.07, "S": 0.29, "M": 0.37, "L": 0.23, "XL": 0.04}   # PANTS(5단계)
SIZE_WEIGHTS_3 = {"S": 0.36, "M": 0.37, "L": 0.27}                            # TOP/CLR/OUT/DRS(3단계, XS+S 합산/L+XL 합산)
SIZE_WEIGHTS_FREE = {"FREE": 1.0}  # ACC

# --- 트렌드 캡슐 라인 (2026.08 추가, 21.Core Product Categories 기준) ---
# 무신사 트렌드 리포트(2025~2026) 반영. 베이직과 달리 한정 판매 후 단종.
# Y3 FW 캡슐(빈티지 데님·안경형 액세서리, 2026.09 예정)은 TODAY 이후라 이번 라운드에서는 제외.
TREND_CAPSULES = [
    {"id": "TRD-CLR-01", "category": "CLR", "name": "톤온톤 니트 셋업",
     "intro": date(2024, 9, 1), "discontinue": date(2025, 2, 28),
     "body_codes": ["WRM", "COOL", "MUT"], "sizes": ["S", "M", "L"], "colors": ["CRM", "ASH"], "price": 45000},
    {"id": "TRD-OUT-01", "category": "OUT", "name": "액티브 반집업 아우터",
     "intro": date(2025, 3, 1), "discontinue": date(2025, 8, 31),
     "body_codes": ["STR", "WAV", "NAT"], "sizes": ["S", "M", "L"], "colors": ["BLK", "GRY"], "price": 79000},
    {"id": "TRD-TOP-01", "category": "TOP", "name": "원숄더 니트탑",
     "intro": date(2025, 9, 1), "discontinue": date(2026, 2, 28),
     "body_codes": ["STR", "WAV", "NAT"], "sizes": ["S", "M", "L"], "colors": ["BLK", "IVR"], "price": 42000},
    {"id": "TRD-OUT-02", "category": "OUT", "name": "뉴트럴 플리스 아우터(그래놀라코어)",
     "intro": date(2025, 9, 1), "discontinue": date(2026, 2, 28),
     "body_codes": ["STR", "WAV", "NAT"], "sizes": ["S", "M", "L"], "colors": ["BRN", "GRN", "BEG"], "price": 79000},
    {"id": "TRD-OUT-03", "category": "OUT", "name": "쿼터집 후드",
     "intro": date(2026, 3, 1), "discontinue": date(2026, 8, 31),
     "body_codes": ["STR", "WAV", "NAT"], "sizes": ["S", "M", "L"], "colors": ["BLK", "BEG"], "price": 69000},
    {"id": "TRD-ACC-01", "category": "ACC", "name": "참키링 액세서리",
     "intro": date(2026, 3, 1), "discontinue": date(2026, 8, 31),
     "body_codes": ["CHM"], "sizes": ["FREE"], "colors": ["BLK", "GLD", "SLV"], "price": 15000},
]


def promo_multiplier(d: date) -> float:
    mult = 1.0
    for (sm, sd), (em, ed), factor, _ in PROMO_WINDOWS:
        if em < sm:  # 연말~연초 걸치는 프로모션(12/15~1/15)
            start_a, end_a = date(d.year, sm, sd), date(d.year, 12, 31)
            start_b, end_b = date(d.year, 1, 1), date(d.year, em, ed)
            if start_a <= d <= end_a or start_b <= d <= end_b:
                mult = max(mult, factor)
        else:
            start, end = date(d.year, sm, sd), date(d.year, em, ed)
            if start <= d <= end:
                mult = max(mult, factor)
    return mult


def dow_factor(d: date) -> float:
    return 1.3 if d.weekday() >= 5 else 0.9


_id_counters = {}


def gen_id(prefix):
    if prefix not in _id_counters:
        _id_counters[prefix] = _count(1)
    return f"{prefix}-{next(_id_counters[prefix]):09d}"


def estimate_aov(d: date) -> int:
    """해당 시점 활성 카테고리들의 SKU 수 가중평균가 x 평균 아이템수로 AOV 근사."""
    total_price_weighted, total_skus = 0, 0
    for meta in CATEGORIES.values():
        if meta["intro"] <= d:
            n_skus = len(meta["body_codes"]) * len(meta["sizes"]) * len(meta["colors"])
            total_price_weighted += meta["price"] * n_skus
            total_skus += n_skus
    avg_price = total_price_weighted / total_skus if total_skus else 40000
    return avg_price * AVG_ITEMS_PER_ORDER


def active_sku_count(d: date) -> int:
    return sum(
        len(m["body_codes"]) * len(m["sizes"]) * len(m["colors"])
        for m in CATEGORIES.values() if m["intro"] <= d
    )


# ---------------------------------------------------------------------------
# 1. DB 초기화 (스키마는 SQLAlchemy로, 데이터는 sqlite3 벌크 insert로)
# ---------------------------------------------------------------------------
import os
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
engine = get_engine(DB_PATH)
init_db(engine)
engine.dispose()

con = sqlite3.connect(DB_PATH)
con.execute("PRAGMA foreign_keys=OFF")   # 벌크 로드 구간에서는 FK 검증 끄고 순서 자유롭게
con.execute("PRAGMA synchronous=OFF")
con.execute("PRAGMA journal_mode=MEMORY")
cur = con.cursor()

# ---------------------------------------------------------------------------
# 2. 마스터 데이터 삽입
# ---------------------------------------------------------------------------
cur.executemany("INSERT INTO category (category_code, name) VALUES (?, ?)",
                 [(c, m["name"]) for c, m in CATEGORIES.items()])

cur.execute("INSERT INTO factory VALUES (?, ?, ?, ?, ?)",
            ("FAC-001", "성진어패럴", 300, 45, "선급30%/잔금70%"))

cur.executemany("INSERT INTO channel VALUES (?, ?, ?, ?)", [
    ("ZIGZAG", "지그재그(직진배송)", 0.15, "월 2회"),
    ("OFFLINE", "오프라인 쇼룸/팝업", 0.0, "-"),
])

cur.executemany("INSERT INTO store VALUES (?, ?, ?, ?, ?)", [
    (sid, s["type"], s["location"], s["open"].isoformat(), s["close"].isoformat() if s["close"] else None)
    for sid, s in STORES.items()
])

STYLE_NAME_TEMPLATES = {
    "TOP": "{body} 스퀘어라인 기본티", "PNT": "{body} 슬랙스", "CLR": "{body} 퍼스널컬러 베이직",
    "OUT": "{body} 드롭숄더 아우터", "ACC": "{body} 액세서리", "DRS": "{body} 체형핏 원피스",
}

sku_pool = {}          # sku_code -> {available, pending_po}
sku_info = {}          # sku_code -> {price, cost, category, line_type}
active_from = {}       # sku_code -> intro date
discontinue_at = {}    # sku_code -> discontinue date (BASIC은 None)
product_rows, sku_rows = [], []

for cat_code, meta in CATEGORIES.items():
    for i, body in enumerate(meta["body_codes"], start=1):
        product_id = f"NQ-{cat_code}-{body}-{i:03d}"
        season_label = ("Y1SS" if meta["intro"] == date(2024, 3, 1) else
                         "Y2SS" if meta["intro"] == date(2025, 3, 1) else "Y3SS")
        product_rows.append((
            product_id, cat_code, STYLE_NAME_TEMPLATES[cat_code].format(body=body),
            body, season_label, "판매중", "BASIC", meta["intro"].isoformat(),
        ))
        price = meta["price"]
        cost = round(price * COST_RATIO)
        for size in meta["sizes"]:
            for color in meta["colors"]:
                sku_code = f"{product_id}-{size}-{color}"
                sku_rows.append((sku_code, product_id, size, color, price, cost))
                sku_pool[sku_code] = {"available": 0, "pending_po": False}
                sku_info[sku_code] = {"price": price, "cost": cost, "category": cat_code, "line_type": "BASIC", "size": size}
                active_from[sku_code] = meta["intro"]
                discontinue_at[sku_code] = None

# 트렌드 캡슐 SKU 생성 (21. Core Product Categories 트렌드 캡슐 라인 참고)
for cap in TREND_CAPSULES:
    if cap["intro"] > TODAY:
        continue  # 아직 미출시 (예: Y3 FW 캡슐)
    for i, body in enumerate(cap["body_codes"], start=1):
        product_id = f"{cap['id']}-{body}-{i:03d}"
        product_rows.append((
            product_id, cap["category"], cap["name"], body,
            ("Y1FW" if cap["intro"].month in (9, 10, 11, 12) and cap["intro"].year == 2024 else
             "Y2SS" if cap["intro"] == date(2025, 3, 1) else
             "Y2FW" if cap["intro"] == date(2025, 9, 1) else "Y3SS"),
            "단종" if cap["discontinue"] < TODAY else "판매중", "TREND", cap["intro"].isoformat(),
        ))
        price, cost = cap["price"], round(cap["price"] * COST_RATIO)
        for size in cap["sizes"]:
            for color in cap["colors"]:
                sku_code = f"{product_id}-{size}-{color}"
                sku_rows.append((sku_code, product_id, size, color, price, cost))
                sku_pool[sku_code] = {"available": 0, "pending_po": False}
                sku_info[sku_code] = {"price": price, "cost": cost, "category": cap["category"], "line_type": "TREND", "size": size}
                active_from[sku_code] = cap["intro"]
                discontinue_at[sku_code] = cap["discontinue"]

cur.executemany("INSERT INTO product VALUES (?, ?, ?, ?, ?, ?, ?, ?)", product_rows)
cur.executemany("INSERT INTO sku VALUES (?, ?, ?, ?, ?, ?)", sku_rows)
con.commit()
n_basic = sum(1 for v in sku_info.values() if v["line_type"] == "BASIC")
n_trend = sum(1 for v in sku_info.values() if v["line_type"] == "TREND")
print(f"카테고리 {len(CATEGORIES)}개 / 스타일 {len(product_rows)}개 / SKU {len(sku_rows)}개 생성 "
      f"(베이직 {n_basic} + 트렌드캡슐 {n_trend})")

# ---------------------------------------------------------------------------
# 3. 분기별 매출목표 -> 판매속도(velocity) 산출 (재고 정책에 선행 필요)
#    01. Master Roadmap 2026.08 개정 목표를 SKU당 일평균 판매속도로 환산.
#    재주문점/파레벨/초도물량은 전부 이 속도 기반으로 동적 계산한다.
# ---------------------------------------------------------------------------
quarter_velocity = []  # (q_start, q_end, velocity_per_sku)
daily_order_target = {}  # date -> int (5번 메인루프에서 사용)
quarter_summary = []

for q_start, q_end, target in QUARTERS:
    full_days = (q_end - q_start).days + 1
    aov_full = estimate_aov(q_start)
    full_total_orders = target / aov_full
    avg_daily_orders_full = full_total_orders / full_days
    n_active_skus = active_sku_count(q_start) or 1
    velocity = (avg_daily_orders_full * AVG_ITEMS_PER_ORDER) / n_active_skus
    quarter_velocity.append((q_start, q_end, velocity))

    # 실제 시뮬레이션 구간(오늘까지)에 대해서만 일별 주문수 배분
    actual_start = max(q_start, LAUNCH_DATE)
    actual_end = min(q_end, TODAY)
    if actual_end < actual_start:
        continue
    actual_days = (actual_end - actual_start).days + 1
    scaled_target = target * actual_days / full_days
    aov = estimate_aov(actual_start)
    total_orders = max(int(round(scaled_target / aov)), 1)

    days = [actual_start + timedelta(n) for n in range(actual_days)]
    weights = np.array([promo_multiplier(d) * dow_factor(d) for d in days])
    probs = weights / weights.sum()
    counts = np.random.multinomial(total_orders, probs)
    for d, c in zip(days, counts):
        daily_order_target[d] = daily_order_target.get(d, 0) + int(c)
    quarter_summary.append((q_start, actual_end, scaled_target, total_orders, round(aov), round(velocity, 2)))

print("\n=== 분기별 타겟 & 판매속도 요약 ===")
for q_start, actual_end, target, orders, aov, vel in quarter_summary:
    print(f"{q_start} ~ {actual_end}: 목표 {target/1e8:.1f}억 / 예상주문 {orders:,}건 / "
          f"AOV {aov:,}원 / SKU당 속도 {vel}건/일")


def velocity_for_date(d: date) -> float:
    """해당 날짜가 속한 분기의 속도와, 리드타임(52일)이 걸치는 다음 분기 속도 중 큰 값을
    사용해 재고를 선제적으로 확보한다 (성장 가속 구간에서 품절 방지)."""
    idx = None
    for i, (qs, qe, v) in enumerate(quarter_velocity):
        if qs <= d <= qe:
            idx = i
            break
    if idx is None:
        return quarter_velocity[-1][2] if d > quarter_velocity[-1][1] else quarter_velocity[0][2]
    v_cur = quarter_velocity[idx][2]
    v_next = quarter_velocity[idx + 1][2] if idx + 1 < len(quarter_velocity) else v_cur
    return max(v_cur, v_next)


def reorder_point_for(d: date) -> int:
    return max(int(velocity_for_date(d) * LEAD_TIME_DAYS * REORDER_BUFFER), 10)


def par_level_for(d: date) -> int:
    return max(int(velocity_for_date(d) * LEAD_TIME_DAYS * PAR_BUFFER), 20)


def safety_stock_for(d: date) -> int:
    return int(reorder_point_for(d) * SAFETY_STOCK_RATIO)


# ---------------------------------------------------------------------------
# 4. 초도 입고 + 쇼룸 사전 비축 (동적 파레벨 기반)
# ---------------------------------------------------------------------------
po_rows, po_item_rows, ledger_rows = [], [], []

TREND_INITIAL_BUFFER = 1.0  # 캡슐은 "소량 정예" 운영 -> 베이직(3.0배)보다 훨씬 적게

for sku_code, intro in active_from.items():
    buffer = TREND_INITIAL_BUFFER if sku_info[sku_code]["line_type"] == "TREND" else INITIAL_BUFFER
    initial_qty = int(velocity_for_date(intro) * LEAD_TIME_DAYS * buffer)
    initial_qty = max(initial_qty, 30 if sku_info[sku_code]["line_type"] == "TREND" else 50)
    po_id = gen_id("PO-INIT")
    po_rows.append((po_id, "FAC-001", (intro - timedelta(days=LEAD_TIME_DAYS)).isoformat(),
                     intro.isoformat(), "입고완료"))
    po_item_rows.append((po_id, sku_code, initial_qty, sku_info[sku_code]["cost"]))
    ledger_rows.append((gen_id("LED"), sku_code, "입고", initial_qty, po_id,
                         datetime.combine(intro, datetime.min.time()).isoformat()))
    sku_pool[sku_code]["available"] = initial_qty

# 쇼룸(상설) 오픈 전 사전 비축: 베이직 라인만 대상 (캡슐은 온라인 중심 소량 운영)
for sid, s in STORES.items():
    if s["type"] != "상설쇼룸":
        continue
    prep_date = s["open"] - timedelta(weeks=SHOWROOM_PREP_WEEKS)
    for sku_code, intro in active_from.items():
        if intro > s["open"] or sku_info[sku_code]["line_type"] == "TREND":
            continue
        bump = max(int(velocity_for_date(s["open"]) * 14), 10)  # 오프라인 2주치 예비물량
        po_id = gen_id("PO-SHOWROOM")
        po_rows.append((po_id, "FAC-001", prep_date.isoformat(), s["open"].isoformat(), "입고완료"))
        po_item_rows.append((po_id, sku_code, bump, sku_info[sku_code]["cost"]))
        ledger_rows.append((gen_id("LED"), sku_code, "입고", bump, po_id,
                             datetime.combine(s["open"], datetime.min.time()).isoformat()))
        sku_pool[sku_code]["available"] += bump

cur.executemany("INSERT INTO purchase_order VALUES (?, ?, ?, ?, ?)", po_rows)
cur.executemany("INSERT INTO po_item (po_id, sku_code, qty, unit_cost) VALUES (?, ?, ?, ?)", po_item_rows)
cur.executemany("INSERT INTO inventory_ledger VALUES (?, ?, ?, ?, ?, ?)", ledger_rows)
con.commit()
print(f"초도 입고 {len(active_from)}건 + 쇼룸 사전비축 PO 처리 완료")
po_rows, po_item_rows, ledger_rows = [], [], []  # 버퍼 초기화

# ---------------------------------------------------------------------------
# 5. 메인 시뮬레이션 루프
# ---------------------------------------------------------------------------
pending_po_arrivals = {}
customer_pool = []
customer_rows, order_rows, order_item_rows, return_rows = [], [], [], []
restock_bump = {}
order_counter = 0
FLUSH_EVERY = 50_000

d = LAUNCH_DATE
while d <= TODAY:
    if d in pending_po_arrivals:
        for sku_code, qty, po_id in pending_po_arrivals[d]:
            sku_pool[sku_code]["available"] += qty
            sku_pool[sku_code]["pending_po"] = False
            ledger_rows.append((gen_id("LED"), sku_code, "입고", qty, po_id,
                                 datetime.combine(d, datetime.min.time()).isoformat()))
        del pending_po_arrivals[d]

    n_orders = daily_order_target.get(d, 0)
    if n_orders > 0:
        active_skus = [s for s, intro in active_from.items()
                       if intro <= d and (discontinue_at[s] is None or d <= discontinue_at[s])
                       and sku_pool[s]["available"] > 0]

        # 날씨(24절기 보간 기온) x 실측 신장분포 기반 SKU 가중치
        # (기온: 기상청 평년값, 신장분포: 2018 설문 기반 사이즈코리아 정합 비율)
        temp_today = get_temp(d)
        sku_weights = []
        for s in active_skus:
            info = sku_info[s]
            w_cat = category_weather_factor(info["category"], temp_today)
            size_map = (SIZE_WEIGHTS_5 if info["category"] == "PNT" else
                        SIZE_WEIGHTS_FREE if info["category"] == "ACC" else SIZE_WEIGHTS_3)
            w_size = size_map.get(info["size"], 1.0)
            sku_weights.append(w_cat * w_size)

        offline_active, offline_store_id = False, None
        for sid, s in STORES.items():
            if s["open"] <= d and (s["close"] is None or d <= s["close"]):
                offline_active, offline_store_id = True, sid
                break

        for _ in range(n_orders):
            if not active_skus:
                break
            order_counter += 1
            order_id = gen_id("ORD")

            if customer_pool and random.random() < 0.30:
                customer_id = random.choice(customer_pool)
            else:
                customer_id = gen_id("CUST")
                persona = "Primary(18-24)" if random.random() < 0.7 else "Secondary(25-28)"
                customer_rows.append((customer_id, persona, "ZIGZAG", d.isoformat()))
                customer_pool.append(customer_id)

            if offline_active and random.random() < 0.05:
                channel_id, store_id = "OFFLINE", offline_store_id
            else:
                channel_id, store_id = "ZIGZAG", None

            n_items = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
            k = min(n_items, len(active_skus))
            chosen = list({s: None for s in random.choices(active_skus, weights=sku_weights, k=k * 2)})[:k]
            if len(chosen) < k:  # 중복 제거 후 부족하면 균등 샘플로 보충
                remain = [s for s in active_skus if s not in chosen]
                chosen += random.sample(remain, k=min(k - len(chosen), len(remain)))
            order_dt = datetime.combine(d, datetime.min.time()) + timedelta(
                hours=random.randint(8, 23), minutes=random.randint(0, 59))

            total_amount, items_payload = 0, []
            for sku_code in chosen:
                if sku_pool[sku_code]["available"] <= 0:
                    continue
                sku_pool[sku_code]["available"] -= 1
                info = sku_info[sku_code]
                total_amount += info["price"]
                items_payload.append((sku_code, info["price"], info["category"]))
                ledger_rows.append((gen_id("LED"), sku_code, "판매출고", -1, order_id, order_dt.isoformat()))

                # 재발주 트리거 (트렌드캡슐은 자동재발주 제외 - 소량 한정 운영 원칙, 24번 문서 참고)
                if (info["line_type"] == "BASIC"
                        and sku_pool[sku_code]["available"] <= reorder_point_for(d)
                        and not sku_pool[sku_code]["pending_po"]):
                    order_qty = par_level_for(d) - sku_pool[sku_code]["available"]
                    po_id = gen_id("PO")
                    arrival = d + timedelta(days=LEAD_TIME_DAYS)
                    po_rows.append((po_id, "FAC-001", d.isoformat(), arrival.isoformat(), "발주"))
                    po_item_rows.append((po_id, sku_code, order_qty, info["cost"]))
                    pending_po_arrivals.setdefault(arrival, []).append((sku_code, order_qty, po_id))
                    sku_pool[sku_code]["pending_po"] = True

                # 반품 여부 즉시 판정 (33번 문서 2026.08 개정: 채널별 처리 차별화)
                rate = CATEGORIES[info["category"]]["return_rate"]
                if random.random() < rate:
                    req_date = d + timedelta(days=random.randint(0, 25) if channel_id == "OFFLINE" else random.randint(5, 25))
                    if req_date <= TODAY:
                        if channel_id == "OFFLINE":
                            reason_code = "R05" if random.random() < 0.7 else random.choices(
                                ["R01", "R02", "R03"], weights=[0.5, 0.2, 0.3])[0]
                            elapsed = (TODAY - req_date).days
                            status = "완료" if elapsed >= 0 else "접수"
                            resolution = random.choices(["교환", "환불"], weights=[0.8, 0.2])[0] if status == "완료" else None
                        else:
                            reason_code = random.choices(["R01", "R02", "R03", "R04"], weights=[0.5, 0.15, 0.25, 0.10])[0]
                            elapsed = (TODAY - req_date).days
                            status = "완료" if elapsed >= 3 else ("검수중" if elapsed >= 1 else "접수")
                            resolution = random.choices(["교환", "환불"], weights=[0.6, 0.4])[0] if status == "완료" else None

                        return_rows.append((gen_id("RET"), order_id, sku_code, reason_code, status,
                                             req_date.isoformat(), resolution))
                        if status == "완료" and reason_code != "R04":
                            resolve_dt = datetime.combine(req_date, datetime.min.time()) + timedelta(
                                hours=2 if channel_id == "OFFLINE" else 72)
                            ledger_rows.append((gen_id("LED"), sku_code, "반품입고", 1, order_id, resolve_dt.isoformat()))
                            restock_bump[sku_code] = restock_bump.get(sku_code, 0) + 1
                        elif reason_code == "R04":
                            ledger_rows.append((gen_id("LED"), sku_code, "불량처리", 0, order_id,
                                                 datetime.combine(req_date, datetime.min.time()).isoformat()))

            if not items_payload:
                order_counter -= 1
                continue

            elapsed = (TODAY - d).days
            status = "구매확정" if elapsed > 35 else ("배송완료" if elapsed > 3 else "배송중")
            order_rows.append((order_id, customer_id, channel_id, store_id, order_dt.isoformat(), status, total_amount))
            for sku_code, price, _cat in items_payload:
                order_item_rows.append((order_id, sku_code, 1, price))

    # 주기적 플러시
    if len(order_rows) >= FLUSH_EVERY:
        cur.executemany("INSERT INTO customer VALUES (?, ?, ?, ?)", customer_rows)
        cur.executemany("INSERT INTO purchase_order VALUES (?, ?, ?, ?, ?)", po_rows)
        cur.executemany("INSERT INTO po_item (po_id, sku_code, qty, unit_cost) VALUES (?, ?, ?, ?)", po_item_rows)
        cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", order_rows)
        cur.executemany("INSERT INTO order_item (order_id, sku_code, qty, unit_price) VALUES (?, ?, ?, ?)", order_item_rows)
        cur.executemany("INSERT INTO inventory_ledger VALUES (?, ?, ?, ?, ?, ?)", ledger_rows)
        cur.executemany("INSERT INTO return_request VALUES (?, ?, ?, ?, ?, ?, ?)", return_rows)
        con.commit()
        print(f"  ...진행 중: {d} 시점까지 주문 {order_counter:,}건 누적 (플러시 완료)")
        customer_rows, po_rows, po_item_rows = [], [], []
        order_rows, order_item_rows, ledger_rows, return_rows = [], [], [], []

    d += timedelta(days=1)

# 잔여 버퍼 플러시
cur.executemany("INSERT INTO customer VALUES (?, ?, ?, ?)", customer_rows)
cur.executemany("INSERT INTO purchase_order VALUES (?, ?, ?, ?, ?)", po_rows)
cur.executemany("INSERT INTO po_item (po_id, sku_code, qty, unit_cost) VALUES (?, ?, ?, ?)", po_item_rows)
cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", order_rows)
cur.executemany("INSERT INTO order_item (order_id, sku_code, qty, unit_price) VALUES (?, ?, ?, ?)", order_item_rows)
cur.executemany("INSERT INTO inventory_ledger VALUES (?, ?, ?, ?, ?, ?)", ledger_rows)
cur.executemany("INSERT INTO return_request VALUES (?, ?, ?, ?, ?, ?, ?)", return_rows)
con.commit()
print(f"\n주문 생성 완료: 총 {order_counter:,}건 (고객 {len(customer_pool):,}명)")

# ---------------------------------------------------------------------------
# 6. Inventory 최종 스냅샷
# ---------------------------------------------------------------------------
for sku_code, bump in restock_bump.items():
    sku_pool[sku_code]["available"] += bump

pending_return_by_sku = {}
cur.execute("SELECT sku_code, COUNT(*) FROM return_request WHERE status != '완료' GROUP BY sku_code")
for sku_code, cnt in cur.fetchall():
    pending_return_by_sku[sku_code] = cnt

inv_rows = []
for sku_code, state in sku_pool.items():
    inv_rows.append((
        sku_code, max(state["available"], 0), 0, 0,
        pending_return_by_sku.get(sku_code, 0), safety_stock_for(TODAY), reorder_point_for(TODAY),
        datetime.combine(TODAY, datetime.min.time()).isoformat(),
    ))
cur.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)", inv_rows)
con.commit()

# ---------------------------------------------------------------------------
# 7. 요약 + 검증
# ---------------------------------------------------------------------------
print("\n=== 최종 테이블 로우 수 ===")
for t in ["category", "product", "sku", "factory", "channel", "store", "customer",
          "orders", "order_item", "purchase_order", "po_item", "inventory",
          "inventory_ledger", "return_request"]:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"{t:16s}: {cur.fetchone()[0]:>10,d}")

print("\n=== 분기별 실제 매출 vs 목표 ===")
for q_start, q_end, target in QUARTERS:
    actual_end = min(q_end, TODAY)
    if actual_end < q_start:
        continue
    cur.execute("SELECT COALESCE(SUM(total_amount),0), COUNT(*) FROM orders WHERE order_date >= ? AND order_date <= ?",
                (q_start.isoformat(), (actual_end + timedelta(days=1)).isoformat()))
    actual_rev, actual_orders = cur.fetchone()
    full_days = (q_end - q_start).days + 1
    actual_days = (actual_end - q_start).days + 1
    scaled_target = target * actual_days / full_days
    print(f"{q_start}~{actual_end}: 목표 {scaled_target/1e8:.1f}억 / 실제 {actual_rev/1e8:.1f}억 "
          f"({actual_rev/scaled_target*100:.0f}%), 주문 {actual_orders:,}건")

con.close()
print("\n✅ nqnq.db 생성 완료 (v2)")
