import io
import os
import re
import secrets
import smtplib
import textwrap
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

import requests
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    send_file, send_from_directory, session, url_for
)
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 Mo max pour le CV

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-cette-cle-secrete-avant-la-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "cv_site.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@localhost")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Merci de vous connecter pour accéder à cette page."
login_manager.login_message_category = "warning"


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(30), default="local")
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship(
        "Profile", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    verification_tokens = db.relationship(
        "EmailVerificationToken", backref="user", cascade="all, delete-orphan"
    )
    reset_tokens = db.relationship(
        "PasswordResetToken", backref="user", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    full_name = db.Column(db.String(150))
    job_title = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    address = db.Column(db.String(200))
    summary = db.Column(db.Text)
    experience = db.Column(db.Text)
    education = db.Column(db.Text)
    skills = db.Column(db.Text)
    linkedin = db.Column(db.String(200))

    cv_filename = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailVerificationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_token():
    return secrets.token_urlsafe(32)


def create_verification_token(user):
    EmailVerificationToken.query.filter_by(user_id=user.id).delete()
    token = generate_token()
    verification = EmailVerificationToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.session.add(verification)
    db.session.commit()
    return token


def create_reset_token(user):
    PasswordResetToken.query.filter_by(user_id=user.id).delete()
    token = generate_token()
    reset_record = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.session.add(reset_record)
    db.session.commit()
    return token


def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value or "cv")
    value = value.strip("-")
    return value.lower() or "cv"


def draw_wrapped_text(c, text, x, y, width, line_height=14):
    lines = textwrap.wrap(text or "", width=width, break_long_words=False)
    if not lines:
        return y
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    return y


def get_oauth_config(provider):
    if provider == "google":
        return {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
        }
    if provider == "microsoft":
        return {
            "client_id": os.environ.get("MICROSOFT_CLIENT_ID"),
            "client_secret": os.environ.get("MICROSOFT_CLIENT_SECRET"),
            "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
            "scope": "openid profile email",
        }
    return None


def send_email_message(recipient, subject, body):
    if not app.config.get("MAIL_SERVER"):
        return False

    message = EmailMessage()
    message["From"] = app.config.get("MAIL_DEFAULT_SENDER")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        server = smtplib.SMTP(app.config["MAIL_SERVER"], int(app.config.get("MAIL_PORT", 587)))
        if app.config.get("MAIL_USE_TLS"):
            server.starttls()
        if app.config.get("MAIL_USERNAME") and app.config.get("MAIL_PASSWORD"):
            server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        server.send_message(message)
        server.quit()
        return True
    except Exception:
        return False


def generate_unique_username(base_name):
    base_name = (base_name or "user").strip()
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "", base_name) or "user"
    candidate = cleaned
    suffix = 1
    while User.query.filter_by(username=candidate).first():
        candidate = f"{cleaned}{suffix}"
        suffix += 1
    return candidate


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    profiles = (
        Profile.query.filter(Profile.full_name.isnot(None))
        .order_by(Profile.updated_at.desc())
        .limit(20)
        .all()
    )
    return render_template("index.html", profiles=profiles)


@app.route("/editor")
@login_required
def editor():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "KOKO.html")


@app.route("/auth/<provider>", methods=["GET", "POST"])
def social_auth(provider):
    if provider not in {"google", "microsoft"}:
        abort(404)

    config = get_oauth_config(provider)
    if request.method == "GET" and config and config["client_id"] and config["client_secret"]:
        redirect_uri = url_for("oauth_callback", provider=provider, _external=True)
        state = secrets.token_urlsafe(32)
        session["oauth_state"] = state
        session["oauth_provider"] = provider
        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
            "state": state,
            "prompt": "consent",
        }
        if provider == "microsoft":
            params["response_mode"] = "query"
        return redirect(f"{config['auth_url']}?{urlencode(params)}")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Veuillez renseigner votre email et un mot de passe pour continuer.", "danger")
            return render_template("social_auth.html", provider=provider)

        user = User.query.filter_by(email=email).first()
        if user is None:
            username = email.split("@", 1)[0]
            username = re.sub(r"[^a-zA-Z0-9_.-]", "", username) or "user"
            username = generate_unique_username(username)
            user = User(username=username, email=email, provider=provider, is_verified=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            profile = Profile(user_id=user.id)
            db.session.add(profile)
            db.session.commit()

        if not user.check_password(password):
            flash("Ce compte n’a pas été créé avec ce mot de passe. Veuillez utiliser le compte associé.", "danger")
            return render_template("social_auth.html", provider=provider)

        login_user(user)
        flash(f"Connexion via {provider.capitalize()} réussie.", "success")
        return redirect(url_for("dashboard"))

    if config and config["client_id"] and config["client_secret"]:
        flash("Connexion OAuth configurée. Le compte sera créé automatiquement si besoin.", "info")
    return render_template("social_auth.html", provider=provider)


@app.route("/auth/<provider>/callback")
def oauth_callback(provider):
    if provider not in {"google", "microsoft"}:
        abort(404)

    config = get_oauth_config(provider)
    if not config or not config["client_id"] or not config["client_secret"]:
        flash("Le fournisseur OAuth n’est pas configuré sur ce serveur.", "warning")
        return redirect(url_for("login"))

    expected_state = session.get("oauth_state")
    if request.args.get("state") != expected_state:
        flash("La session OAuth a expiré ou est invalide. Réessayez.", "danger")
        return redirect(url_for("login"))

    code = request.args.get("code")
    if not code:
        flash("Le code OAuth n’a pas été fourni par le fournisseur.", "danger")
        return redirect(url_for("login"))

    token_payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": url_for("oauth_callback", provider=provider, _external=True),
    }
    try:
        token_response = requests.post(config["token_url"], data=token_payload, timeout=30)
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Aucun access_token reçu")

        userinfo_response = requests.get(
            config["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except Exception:
        flash("La connexion OAuth a échoué. Merci de réessayer.", "danger")
        return redirect(url_for("login"))

    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").strip().lower()
    if not email:
        flash("Le fournisseur OAuth n’a pas renvoyé d’adresse e-mail valide.", "danger")
        return redirect(url_for("login"))

    user = User.query.filter_by(email=email).first()
    if user is None:
        name = userinfo.get("name") or email.split("@", 1)[0]
        username = generate_unique_username(name)
        user = User(username=username, email=email, provider=provider, is_verified=True)
        user.set_password(secrets.token_urlsafe(24))
        db.session.add(user)
        db.session.commit()

        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

    login_user(user)
    session.pop("oauth_state", None)
    session.pop("oauth_provider", None)
    flash(f"Connexion via {provider.capitalize()} réussie.", "success")
    return redirect(url_for("dashboard"))


@app.route("/verify/<token>")
def verify_email(token):
    record = EmailVerificationToken.query.filter_by(token=token).first()
    if not record:
        flash("Le lien de vérification est invalide ou a déjà été utilisé.", "danger")
        return redirect(url_for("login"))

    if record.expires_at < datetime.utcnow():
        db.session.delete(record)
        db.session.commit()
        flash("Le lien de vérification a expiré. Demandez un nouveau compte ou une nouvelle vérification.", "warning")
        return redirect(url_for("register"))

    user = record.user
    user.is_verified = True
    user.email_verified_at = datetime.utcnow()
    db.session.delete(record)
    db.session.commit()
    flash("Votre adresse e-mail a été vérifiée avec succès.", "success")
    return redirect(url_for("login"))


@app.route("/verify-pending")
def verify_pending():
    return render_template("verify_pending.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = create_reset_token(user)
            reset_url = url_for("reset_password", token=token, _external=True)
            if send_email_message(
                user.email,
                "Réinitialisation de votre mot de passe",
                f"Cliquer sur ce lien pour réinitialiser votre mot de passe : {reset_url}",
            ):
                flash("Un email de réinitialisation a été envoyé à votre adresse.", "success")
            else:
                flash(f"Lien de réinitialisation généré : {reset_url}", "info")
        else:
            flash("Si un compte correspond à cet email, un lien de réinitialisation vous sera envoyé.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    record = PasswordResetToken.query.filter_by(token=token).first()
    if not record or record.expires_at < datetime.utcnow():
        flash("Le lien de réinitialisation est invalide ou a expiré.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
            return render_template("reset_password.html", token=token)
        if password != confirm:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return render_template("reset_password.html", token=token)

        user = record.user
        user.set_password(password)
        db.session.delete(record)
        db.session.commit()
        flash("Votre mot de passe a été réinitialisé avec succès.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Tous les champs sont obligatoires.", "danger")
            return render_template("register.html")
        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return render_template("register.html")
        if User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur est déjà pris.", "danger")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("Cet email est déjà utilisé.", "danger")
            return render_template("register.html")

        user = User(username=username, email=email, provider="local", is_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

        token = create_verification_token(user)
        verify_link = url_for("verify_email", token=token, _external=True)
        email_sent = send_email_message(
            user.email,
            "Vérification de votre compte",
            f"Merci de vérifier votre compte en cliquant sur ce lien : {verify_link}",
        )
        if email_sent:
            flash("Compte créé avec succès. Un email de vérification a été envoyé.", "success")
        else:
            flash(
                f"Compte créé avec succès. Vérifiez votre email en suivant ce lien : {verify_link}",
                "success",
            )
        return redirect(url_for("verify_pending"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifiant = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifiant) | (User.email == identifiant.lower())
        ).first()

        if user and user.check_password(password):
            if not user.is_verified:
                flash("Votre compte n’est pas vérifié. Vérifiez votre email pour continuer.", "warning")
                return redirect(url_for("verify_pending"))
            login_user(user)
            flash("Connexion réussie.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        flash("Identifiants incorrects.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", profile=current_user.profile)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile = current_user.profile
    if profile is None:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        profile.full_name = request.form.get("full_name", "").strip()
        profile.job_title = request.form.get("job_title", "").strip()
        profile.phone = request.form.get("phone", "").strip()
        profile.address = request.form.get("address", "").strip()
        profile.summary = request.form.get("summary", "").strip()
        profile.experience = request.form.get("experience", "").strip()
        profile.education = request.form.get("education", "").strip()
        profile.skills = request.form.get("skills", "").strip()
        profile.linkedin = request.form.get("linkedin", "").strip()

        file = request.files.get("cv_file")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Format de fichier non autorisé (PDF, DOC, DOCX uniquement).", "danger")
                return render_template("profile.html", profile=profile)

            filename = secure_filename(f"user_{current_user.id}_{file.filename}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            if profile.cv_filename and profile.cv_filename != filename:
                old_path = os.path.join(app.config["UPLOAD_FOLDER"], profile.cv_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)

            profile.cv_filename = filename

        db.session.commit()
        flash("Profil mis à jour avec succès.", "success")
        return redirect(url_for("dashboard"))

    return render_template("profile.html", profile=profile)


@app.route("/profile/export-pdf")
@login_required
def export_profile_pdf():
    profile = current_user.profile
    if profile is None:
        abort(404)

    filename = f"{slugify(profile.full_name or current_user.username)}-cv.pdf"
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setTitle(f"{profile.full_name or current_user.username} - CV")
    c.setFillColorRGB(0.18, 0.36, 0.32)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, y, profile.full_name or current_user.username)
    y -= 28

    c.setFillColorRGB(0.0, 0.0, 0.0)
    c.setFont("Helvetica-Bold", 12)
    if profile.job_title:
        c.drawString(50, y, profile.job_title)
        y -= 22

    if profile.phone:
        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"Téléphone : {profile.phone}")
        y -= 18
    if profile.address:
        c.drawString(50, y, f"Adresse : {profile.address}")
        y -= 18
    if profile.linkedin:
        c.drawString(50, y, f"LinkedIn / Portfolio : {profile.linkedin}")
        y -= 18
    if current_user.email:
        c.drawString(50, y, f"Email : {current_user.email}")
        y -= 18

    if y < 200:
        c.showPage()
        y = height - 50

    if profile.summary:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Résumé")
        y -= 18
        c.setFont("Helvetica", 11)
        y = draw_wrapped_text(c, profile.summary, 50, y, 90)
        y -= 18

    if profile.experience:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Expérience")
        y -= 18
        c.setFont("Helvetica", 11)
        y = draw_wrapped_text(c, profile.experience, 50, y, 90)
        y -= 18

    if profile.education:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Formation")
        y -= 18
        c.setFont("Helvetica", 11)
        y = draw_wrapped_text(c, profile.education, 50, y, 90)
        y -= 18

    if profile.skills:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Compétences")
        y -= 18
        c.setFont("Helvetica", 11)
        y = draw_wrapped_text(c, profile.skills, 50, y, 90)

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/cv/<int:user_id>")
def view_public_profile(user_id):
    user = db.session.get(User, user_id)
    if not user or not user.profile or not user.profile.full_name:
        abort(404)
    return render_template("public_profile.html", profile=user.profile, user=user)


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    expected_prefix = f"user_{current_user.id}_"
    if not filename.startswith(expected_prefix):
        abort(403)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
