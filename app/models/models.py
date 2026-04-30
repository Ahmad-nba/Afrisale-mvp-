from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    size: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    gcs_uri: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    public_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/jpeg")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vector_datapoint_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # JSON-encoded list of floats (1408-dim multimodal embedding). Empty for
    # legacy rows; used by the local cosine-similarity search path.
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    product: Mapped["Product"] = relationship(back_populates="images")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    conversation_state: Mapped["ConversationState | None"] = relationship(
        back_populates="customer",
        uselist=False,
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="whatsapp")
    message_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")

    customer: Mapped["Customer"] = relationship(back_populates="messages")
    attachments: Mapped[list["MessageAttachment"]] = relationship(back_populates="message")


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="image")
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="twilio")
    provider_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    gcs_uri: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    public_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    bytes_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    message: Mapped["Message"] = relationship(back_populates="attachments")


class CustomerEntity(Base):
    __tablename__ = "customer_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        unique=True,
    )
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    customer: Mapped["Customer"] = relationship(back_populates="conversation_state")
