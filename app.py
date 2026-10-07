import base64
import os
from functools import wraps

import pandas as pd
import plotly.graph_objects as go
import requests
from dotenv import load_dotenv
from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, send_from_directory)
from sqlalchemy import create_engine

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = BASE_DIR

app = Flask(__name__, template_folder=BASE_DIR)
app.secret_key = os.getenv("SECRET_KEY", "change-me")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB

# ---------------- قاعدة البيانات ----------------
# على الاستضافة: DATABASE_URL (رابط واحد). محلياً: متغيرات DB_* من .env
db_url = os.getenv("DATABASE_URL")
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    db_url = "postgresql+psycopg2://{u}:{p}@{h}:{port}/{d}".format(
        u=os.getenv("DB_USER"), p=os.getenv("DB_PASSWORD"),
        h=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        d=os.getenv("DB_NAME"),
    )
engine = create_engine(db_url, pool_pre_ping=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------- حماية صفحات الأدمن ----------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if (not ADMIN_PASSWORD or not auth
                or auth.username != ADMIN_USER
                or auth.password != ADMIN_PASSWORD):
            return Response("Login required", 401,
                            {"WWW-Authenticate": 'Basic realm="Admin"'})
        return f(*args, **kwargs)
    return wrapper


# ---------------- الصفحات العامة ----------------
@app.route("/")
def landing():
    return redirect("/admin")


@app.route("/login.html")
def login_page():
    return send_from_directory(PAGES_DIR, "login.html")


@app.route("/almesbah.html")
def almesbah_page():
    return send_from_directory(PAGES_DIR, "almesbah.html")


def build_signal_context():
    """يجلب آخر إشارة من الجدول ويجهز بيانات القالب. يرجع (dict, None) أو (None, رسالة)."""
    query = """
        SELECT * FROM last_forecast_onehour
        ORDER BY "DateTime" DESC
        LIMIT 1
    """
    try:
        df = pd.read_sql(query, engine)
    except Exception:
        return None, "حدث خطأ عند جلب البيانات"
    if df.empty:
        return None, "لا توجد بيانات لعرضها."

    latest = df.iloc[0]
    d = latest.get("Decision", "")
    try:
        price = f"{float(latest.get('Predicted_Close')):.2f}"
    except (TypeError, ValueError):
        price = "N/A"

    return {
        "datetime": pd.to_datetime(latest["DateTime"]).strftime("%Y-%m-%d %H:%M:%S"),
        "price": price,
        "decision": "{} {}".format(
            {"Buy": "🟢", "Sell": "🔴", "Hold": "🟡"}.get(d, "⚪"),
            {"Buy": "صعود", "Sell": "هبوط", "Hold": "انتظار"}.get(d, "غير محدد")),
        "color": {"Buy": "green", "Sell": "red", "Hold": "orange"}.get(d, "black"),
    }, None


@app.route("/last")
def display_last_forecast():
    ctx, err = build_signal_context()
    if err:
        return err, (500 if "خطأ" in err else 200)
    return render_template("display_last_forecast.html", is_admin=False, **ctx)


@app.route("/chart")
def chart():
    df = pd.read_sql("SELECT * FROM gold_trading", engine)
    df["DateTime"] = pd.to_datetime(df["DateTime"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["DateTime"], y=df["Close"], mode="lines",
                             name="السعر الحقيقي",
                             line=dict(color="#1f77b4", width=2)))
    fig.add_trace(go.Scatter(x=df["DateTime"], y=df["Predicted_Close"], mode="lines",
                             name="السعر المتوقع",
                             line=dict(color="green", width=2, dash="dot")))

    colors = {"Buy": "green", "Sell": "red", "Hold": "orange"}
    symbols = {"Buy": "triangle-up", "Sell": "triangle-down", "Hold": "circle"}
    for decision in ["Buy", "Sell", "Hold"]:
        subset = df[df["Decision"] == decision]
        fig.add_trace(go.Scatter(x=subset["DateTime"], y=subset["Close"],
                                 mode="markers", name=decision,
                                 marker=dict(size=12, color=colors[decision],
                                             symbol=symbols[decision])))

    fig.update_layout(title="📈 Almesbah Smart System for Gold Price Prediction",
                      height=600, template="plotly_white",
                      xaxis_title="الوقت", yaxis_title="السعر",
                      hovermode="x unified")

    # include_plotlyjs="cdn" يجعل الصفحة أخف بكثير من تضمين المكتبة كاملة
    return render_template("index.html",
                           chart=fig.to_html(full_html=False, include_plotlyjs="cdn"))


# ---------------- صفحات الأدمن (محمية بكلمة مرور) ----------------
def handle_csv_upload(table_name, template, clean_columns):
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("❌ لم يتم اختيار ملف")
            return redirect(request.url)
        if not file.filename.lower().endswith(".csv"):
            flash("❌ الملف يجب أن يكون CSV")
            return redirect(request.url)

        path = os.path.join(UPLOAD_FOLDER, "upload.csv")
        file.save(path)
        try:
            df = pd.read_csv(path)
            if clean_columns:
                df.columns = df.columns.str.strip().str.replace(" ", "_")
            df.to_sql(table_name, engine, if_exists="replace", index=False)
            flash("✅ تم رفع البيانات بنجاح")
        except Exception as e:
            flash(f"❌ خطأ أثناء رفع البيانات: {e}")
        return redirect(request.url)
    return render_template(template)


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_upload_last():
    # رفع آخر توقع -> جدول last_forecast_onehour
    return handle_csv_upload("last_forecast_onehour",
                             "upload_last_forecast.html", clean_columns=True)


@app.route("/admin/history", methods=["GET", "POST"])
@admin_required
def admin_upload_history():
    # رفع السجل الكامل -> جدول gold_trading (صفحة /chart)
    return handle_csv_upload("gold_trading", "upload.html", clean_columns=False)


@app.route("/admin/last")
@admin_required
def admin_last():
    ctx, err = build_signal_context()
    if err:
        return err
    return render_template("display_last_forecast.html", is_admin=True, **ctx)


@app.route("/admin/send-signal-image", methods=["POST"])
@admin_required
def send_signal_image():
    data = request.get_json(silent=True) or {}
    image_data = data.get("image", "")
    if "," not in image_data:
        return jsonify({"ok": False, "error": "bad image"}), 400

    image_bytes = base64.b64decode(image_data.split(",")[1])
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID},
                      files={"photo": ("signal.png", image_bytes, "image/png")},
                      timeout=20)
    return jsonify({"ok": r.ok})


if __name__ == "__main__":
    app.run(debug=True)
