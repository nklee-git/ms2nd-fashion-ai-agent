"""
홀세일/입점 채널 파일럿 거래 데이터 추가 스크립트
근거 문서: 42. Channel & Settlement Terms (2026.08 개정 - 파일럿 2026.06 시작)

기존 nqnq.db / nqnq_scenario_miss.db에 이미 생성된 데이터 위에, 2026.06.01~TODAY 기간
홀세일 파트너 8곳의 벌크 주문을 추가로 삽입한다. 기존 온라인/오프라인 데이터는 건드리지 않음.
"""
import random
import sqlite3
from datetime import date, datetime, timedelta
from itertools import count as _count

random.seed(7)

TODAY = date(2026, 8, 9)
PILOT_START = date(2026, 6, 1)
WHOLESALE_PRICE_RATIO = 0.45  # 정가 대비 도매공급가
N_PARTNERS = 8
ORDER_INTERVAL_DAYS = 14  # 파트너당 격주 주문

PARTNER_NAMES = [
    "성수 편집숍 A", "홍대 편집숍 B", "강남 백화점 영캐주얼관", "부산 편집숍 C",
    "대구 백화점 영캐주얼관", "온라인 편집숍 D(자체몰)", "제주 편집숍 E", "인천 편집숍 F",
]


def add_wholesale(db_path: str):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=OFF")
    cur = con.cursor()

    # 카운터: 기존 ID와 충돌 없게 별도 프리픽스 사용
    counter = _count(1)

    def gen_id(prefix):
        return f"{prefix}-WS{next(counter):06d}"

    # 1) 홀세일 파트너를 CUSTOMER로 등록
    partner_ids = []
    for name in PARTNER_NAMES[:N_PARTNERS]:
        cid = gen_id("CUST")
        cur.execute("INSERT INTO customer VALUES (?, ?, ?, ?)",
                    (cid, f"Wholesale Partner ({name})", "WHOLESALE", PILOT_START.isoformat()))
        partner_ids.append(cid)

    # 2) 현재 재고 스냅샷에서 BASIC 라인 & 재고 여유 있는 SKU만 대상으로
    cur.execute("""
        SELECT s.sku_code, s.price, i.available_qty
        FROM sku s
        JOIN product p ON s.product_id = p.product_id
        JOIN inventory i ON i.sku_code = s.sku_code
        WHERE p.line_type = 'BASIC' AND i.available_qty > 100
    """)
    candidate_skus = cur.fetchall()  # (sku_code, price, available_qty)
    print(f"  홀세일 대상 SKU 후보: {len(candidate_skus)}개")

    inv_delta = {}  # sku_code -> 차감할 총량
    order_rows, order_item_rows, ledger_rows = [], [], []
    total_orders, total_revenue = 0, 0

    for partner_id in partner_ids:
        d = PILOT_START
        while d <= TODAY:
            n_skus = random.randint(8, 15)
            chosen = random.sample(candidate_skus, k=min(n_skus, len(candidate_skus)))
            order_id = gen_id("ORD")
            order_dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=random.randint(9, 17))
            total_amount = 0
            items = []
            for sku_code, price, avail in chosen:
                already_used = inv_delta.get(sku_code, 0)
                remaining = avail - already_used
                qty = random.randint(15, 35)
                if remaining < qty:
                    continue
                unit_price = round(price * WHOLESALE_PRICE_RATIO)
                total_amount += unit_price * qty
                items.append((sku_code, qty, unit_price))
                inv_delta[sku_code] = already_used + qty
                ledger_rows.append((gen_id("LED"), sku_code, "판매출고", -qty, order_id, order_dt.isoformat()))

            if not items:
                d += timedelta(days=ORDER_INTERVAL_DAYS)
                continue

            order_rows.append((order_id, partner_id, "WHOLESALE", None, order_dt.isoformat(), "구매확정", total_amount))
            for sku_code, qty, unit_price in items:
                order_item_rows.append((order_id, sku_code, qty, unit_price))

            total_orders += 1
            total_revenue += total_amount
            d += timedelta(days=ORDER_INTERVAL_DAYS)

    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", order_rows)
    cur.executemany("INSERT INTO order_item (order_id, sku_code, qty, unit_price) VALUES (?, ?, ?, ?)", order_item_rows)
    cur.executemany("INSERT INTO inventory_ledger VALUES (?, ?, ?, ?, ?, ?)", ledger_rows)

    # 3) 재고 스냅샷 차감 반영
    for sku_code, qty in inv_delta.items():
        cur.execute("UPDATE inventory SET available_qty = available_qty - ? WHERE sku_code = ?", (qty, sku_code))

    con.commit()
    print(f"  홀세일 주문 {total_orders}건 추가, 매출 {total_revenue/1e8:.2f}억 (파트너 {N_PARTNERS}곳)")
    con.close()


if __name__ == "__main__":
    for db in ["nqnq.db", "nqnq_scenario_miss.db"]:
        print(f"[{db}]")
        add_wholesale(db)
