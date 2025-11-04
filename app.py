# app.py
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import jwt

# === إعدادات ===
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# دعم PostgreSQL على Render + SQLite محلي
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    # تطوير محلي: SQLite
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instaboost.db')}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
CORS(app)

# === النماذج ===
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    service_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    amount_usd = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="pending")
    instagram_target = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# إنشاء الجداول عند التشغيل
with app.app_context():
    db.create_all()

# === وظائف مساعدة ===
def create_token(username):
    return jwt.encode({"sub": username}, SECRET_KEY, algorithm="HS256")

# === المسارات ===
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or not all(k in data for k in ("username", "email", "password")):
        return jsonify({"error": "Missing fields"}), 400
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Username exists"}), 400
    hashed = generate_password_hash(data["password"])
    user = User(username=data["username"], email=data["email"], password_hash=hashed)
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "username": user.username}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or not all(k in data for k in ("username", "password")):
        return jsonify({"error": "Missing credentials"}), 400
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_token(user.username)
    return jsonify({"access_token": token, "token_type": "bearer"})

@app.route("/api/orders/free-trial", methods=["POST"])
def free_trial():
    data = request.get_json()
    if not data or "instagram_target" not in data:
        return jsonify({"error": "instagram_target required"}), 400
    user = User.query.first()
    if not user:
        return jsonify({"error": "Register first"}), 400
    order = Order(
        user_id=user.id,
        service_type="followers_likes",
        quantity=20,
        amount_usd="0.00",
        instagram_target=data["instagram_target"]
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"id": order.id, "status": "pending"}), 201

@app.route("/api/orders/paid", methods=["POST"])
def paid_order():
    data = request.get_json()
    if not all(k in data for k in ("service_type", "quantity", "amount_usd", "instagram_target")):
        return jsonify({"error": "Missing fields"}), 400
    service = data["service_type"]
    qty = data["quantity"]
    provided = data["amount_usd"]
    if service == "followers" and qty >= 100:
        expected = f"{qty * 0.002:.2f}"
    elif service == "likes" and qty >= 100:
        expected = f"{qty * 0.001:.2f}"
    else:
        return jsonify({"error": "Min 100, service: followers/likes"}), 400
    if provided != expected:
        return jsonify({"error": f"Expected ${expected}"}), 400
    user = User.query.first()
    if not user:
        return jsonify({"error": "Register first"}), 400
    order = Order(
        user_id=user.id,
        service_type=service,
        quantity=qty,
        amount_usd=provided,
        instagram_target=data["instagram_target"]
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"id": order.id, "status": "pending"}), 201

@app.route("/api/reviews", methods=["POST"])
def create_review():
    data = request.get_json()
    if not data or "rating" not in data or "comment" not in data or not (1 <= data["rating"] <= 5):
        return jsonify({"error": "Valid rating (1-5) and comment required"}), 400
    user = User.query.first()
    if not user:
        return jsonify({"error": "Register first"}), 400
    review = Review(user_id=user.id, rating=data["rating"], comment=data["comment"])
    db.session.add(review)
    db.session.commit()
    return jsonify({"id": review.id}), 201

@app.route("/api/reviews", methods=["GET"])
def get_reviews():
    reviews = Review.query.all()
    return jsonify([{"id": r.id, "rating": r.rating, "comment": r.comment} for r in reviews])

# === دردشة الدعم (بدون WebSocket) ===
@app.route("/api/chat/send", methods=["POST"])
def send_chat_message():
    data = request.get_json()
    if not data or "message" not in data or "name" not in 
        return jsonify({"error": "name and message required"}), 400
    msg = SupportMessage(name=data["name"], message=data["message"])
    db.session.add(msg)
    db.session.commit()
    return jsonify({"status": "sent"}), 201

@app.route("/api/chat/messages", methods=["GET"])
def get_chat_messages():
    messages = SupportMessage.query.order_by(SupportMessage.created_at).all()
    return jsonify([
        {"name": m.name, "message": m.message, "is_admin": m.is_admin}
        for m in messages
    ])

# === الصفحة الجذر ===
@app.route("/")
def root():
    return jsonify({"message": "InstaBoost API - Ready for Render!"})

# === التشغيل المحلي ===
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
