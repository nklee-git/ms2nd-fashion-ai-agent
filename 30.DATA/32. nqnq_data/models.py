"""
NQNQ 데이터 모델 (SQLAlchemy)
근거 문서: 70. Data Model & Architecture / 71. Entity Definitions & Data Dictionary
           70. Data Model & Architecture / 72. Entity Relationship Diagram

설계 원칙 (73. Local-First Architecture & Migration Plan 참고):
- 모든 PK는 문자열(string)로 선언 -> DB 엔진 교체 시 오토인크리먼트 방식 차이로 인한 충돌 방지
- 날짜/시간은 표준 Date/DateTime 타입 사용 (SQLite는 내부적으로 ISO8601 문자열로 저장됨)
- FK 제약조건을 명시적으로 선언 (SQLite는 기본 비활성화이므로 엔진 생성 시 PRAGMA foreign_keys=ON 필요)
- 이 파일은 DB 엔진에 무관한 표준 SQLAlchemy ORM 코드 -> engine 생성 시 connection string만
  바꾸면 SQLite -> PostgreSQL 전환 가능 (create_engine("postgresql://...") 등)
"""

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Date, DateTime,
    ForeignKey, event
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine import Engine

Base = declarative_base()


# SQLite는 기본적으로 FK 제약을 강제하지 않으므로, 커넥션 생성 시마다 PRAGMA를 켜준다.
# (73. Local-First Architecture & Migration Plan의 마이그레이션 친화적 설계 원칙 #3)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Category(Base):
    __tablename__ = "category"
    category_code = Column(String, primary_key=True)   # TOP / PNT / CLR / OUT / ACC / DRS
    name = Column(String, nullable=False)


class Product(Base):
    __tablename__ = "product"
    product_id = Column(String, primary_key=True)
    category_code = Column(String, ForeignKey("category.category_code"), nullable=False)
    style_name = Column(String, nullable=False)
    body_tone_code = Column(String, nullable=False)     # STR/WAV/NAT, 5LT/PLT, WRM/COOL/MUT ...
    season = Column(String, nullable=False)             # Y1SS, Y1FW, Y2SS ...
    status = Column(String, nullable=False)             # 기획중/샘플링중/생산중/판매중/품절/단종
    line_type = Column(String, nullable=False, default="BASIC")  # BASIC / TREND (2026.08 추가)
    popularity_tier = Column(String, nullable=False, default="STEADY")  # HERO/STEADY/NICHE (2026.08 추가)
    launch_date = Column(Date)


class Sku(Base):
    __tablename__ = "sku"
    sku_code = Column(String, primary_key=True)         # NQ-TOP-STR-001-M-BLK
    product_id = Column(String, ForeignKey("product.product_id"), nullable=False)
    size = Column(String, nullable=False)
    color_code = Column(String, nullable=False)
    price = Column(Integer, nullable=False)             # 정가(원)
    cost = Column(Integer, nullable=False)              # 원가(원단+공임+물류, COGS)


class Factory(Base):
    __tablename__ = "factory"
    factory_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    moq = Column(Integer)
    lead_time_days = Column(Integer)
    payment_terms = Column(String)


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"
    po_id = Column(String, primary_key=True)
    factory_id = Column(String, ForeignKey("factory.factory_id"), nullable=False)
    order_date = Column(Date, nullable=False)
    expected_arrival_date = Column(Date, nullable=False)
    status = Column(String, nullable=False)             # 발주/생산중/검수중/입고완료


class PoItem(Base):
    __tablename__ = "po_item"
    id = Column(Integer, primary_key=True, autoincrement=True)  # 내부 surrogate key
    po_id = Column(String, ForeignKey("purchase_order.po_id"), nullable=False)
    sku_code = Column(String, ForeignKey("sku.sku_code"), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_cost = Column(Integer, nullable=False)


class Inventory(Base):
    __tablename__ = "inventory"
    sku_code = Column(String, ForeignKey("sku.sku_code"), primary_key=True)
    available_qty = Column(Integer, default=0)
    reserved_qty = Column(Integer, default=0)
    defective_qty = Column(Integer, default=0)
    pending_return_qty = Column(Integer, default=0)
    safety_stock = Column(Integer, default=40)
    reorder_point = Column(Integer, default=60)
    last_updated = Column(DateTime)


class InventoryLedger(Base):
    __tablename__ = "inventory_ledger"
    ledger_id = Column(String, primary_key=True)
    sku_code = Column(String, ForeignKey("sku.sku_code"), nullable=False)
    movement_type = Column(String, nullable=False)      # 입고/판매출고/반품입고/불량처리/이관
    qty_change = Column(Integer, nullable=False)         # +/-
    reference_id = Column(String)                        # order_id 또는 po_id
    movement_date = Column(DateTime, nullable=False)


class Channel(Base):
    __tablename__ = "channel"
    channel_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    commission_rate = Column(Float)
    settlement_cycle = Column(String)


class Customer(Base):
    __tablename__ = "customer"
    customer_id = Column(String, primary_key=True)
    persona_segment = Column(String)                     # Primary(18-24)/Secondary(25-28)
    signup_channel = Column(String)
    signup_date = Column(Date)


class Store(Base):
    __tablename__ = "store"
    store_id = Column(String, primary_key=True)
    type = Column(String, nullable=False)                # 팝업/상설쇼룸
    location = Column(String)
    open_date = Column(Date)
    close_date = Column(Date)                             # nullable, 팝업만


class Order(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customer.customer_id"), nullable=False)
    channel_id = Column(String, ForeignKey("channel.channel_id"), nullable=False)
    store_id = Column(String, ForeignKey("store.store_id"), nullable=True)
    order_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)               # 주문완료/배송중/배송완료/구매확정/취소
    total_amount = Column(Integer, nullable=False)


class OrderItem(Base):
    __tablename__ = "order_item"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("orders.order_id"), nullable=False)
    sku_code = Column(String, ForeignKey("sku.sku_code"), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)


class ReturnRequest(Base):
    __tablename__ = "return_request"
    return_id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.order_id"), nullable=False)
    sku_code = Column(String, ForeignKey("sku.sku_code"), nullable=False)  # 주문 내 반품 대상 SKU (라인아이템 단위)
    reason_code = Column(String, nullable=False)          # R01~R05
    status = Column(String, nullable=False)                # 접수/검수중/완료
    request_date = Column(Date, nullable=False)
    resolution = Column(String)                             # 환불/교환


def get_engine(db_path="nqnq.db"):
    return create_engine(f"sqlite:///{db_path}")


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session(engine):
    return sessionmaker(bind=engine)()
