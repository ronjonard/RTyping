import os
import hashlib
import secrets
import logging
import requests

from datetime import datetime, timedelta

import mysql.connector
from mysql.connector import IntegrityError
from dotenv import load_dotenv

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify
)

from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-development-key")
app.logger.setLevel(logging.INFO)


# MySQL connection
def get_db_connection():
    connection_options = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "Rtyping")
    }

    ssl_ca = os.getenv("DB_SSL_CA")

    if ssl_ca:
        connection_options["ssl_ca"] = ssl_ca
        connection_options["ssl_verify_cert"] = True

    return mysql.connector.connect(**connection_options)


# Send password-reset email using Resend

def send_reset_email(recipient, reset_link):
    gas_url = os.getenv("GAS_EMAIL_URL")
    gas_secret = os.getenv("GAS_EMAIL_SECRET")

    if not gas_url or not gas_secret:
        raise RuntimeError("Google Apps Script settings are missing.")

    payload = {
        "token": gas_secret,
        "to": recipient,
        "subject": "Reset Your RTyping Password",
        "body": (
            "Hello,\n\n"
            "We received a request to reset your RTyping password.\n\n"
            f"Use this link to choose a new password:\n{reset_link}\n\n"
            "This link expires in 30 minutes and can only be used once.\n"
            "If you did not request this, you can ignore this email.\n"
        )
    }

    response = requests.post(
        gas_url,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("success"):
        raise RuntimeError(
            result.get("message", "Email sending failed.")
        )



# Homepage
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


# Sign Up
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        def registration_error(message):
            flash(message, "error")
            return render_template(
                "register.html",
                username=username,
                email=email
            )

        if not username or not email or not password or not confirm_password:
            return registration_error("Please fill in all fields.")

        if len(username) > 50 or len(email) > 100:
            return registration_error("Your username or email is too long.")

        if len(password) < 8:
            return registration_error("Password must be at least 8 characters.")

        if password != confirm_password:
            return registration_error("Passwords do not match.")

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (username, email, generate_password_hash(password))
            )

            conn.commit()

            flash(
                "Account created successfully! You can now sign in.",
                "success"
            )
            return redirect(url_for("login"))

        except IntegrityError:
            if conn and conn.is_connected():
                conn.rollback()

            return registration_error(
                "That email address is already registered."
            )

        except mysql.connector.Error:
            if conn and conn.is_connected():
                conn.rollback()

            app.logger.exception("Registration database error")

            return registration_error(
                "Unable to create your account. Please try again."
            )

        finally:
            if cursor:
                cursor.close()

            if conn and conn.is_connected():
                conn.close()

    return render_template("register.html")


# Sign In
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT user_id, username, password_hash
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]

                flash("You are now signed in!")
                return redirect(url_for("index"))

            flash("Incorrect email or password.")
            return redirect(url_for("login"))

        except mysql.connector.Error:
            app.logger.exception("Login database error")
            flash("Unable to sign in right now. Please try again.")
            return redirect(url_for("login"))

        finally:
            if cursor:
                cursor.close()

            if conn and conn.is_connected():
                conn.close()

    return render_template("login.html")


# Sign Out
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have signed out.")
    return redirect(url_for("index"))


# Forgot Password
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT user_id FROM users WHERE email = %s",
                (email,)
            )

            user = cursor.fetchone()

            if user:
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                expires_at = datetime.utcnow() + timedelta(minutes=30)

                cursor.execute(
                    """
                    INSERT INTO password_resets
                        (user_id, token_hash, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (user["user_id"], token_hash, expires_at)
                )

                conn.commit()

                reset_link = url_for(
                    "reset_password",
                    token=token,
                    _external=True
                )

                try:
                    send_reset_email(email, reset_link)
                    app.logger.info("Password-reset email sent successfully.")

                except Exception:
                    app.logger.exception("Password-reset email failed")

            flash(
                "If that email is registered, a reset link will be sent "
                "if email delivery is available."
            )

            return redirect(url_for("login"))

        except mysql.connector.Error:
            if conn and conn.is_connected():
                conn.rollback()

            app.logger.exception("Forgot-password database error")
            flash("Unable to process your request right now.")
            return redirect(url_for("forgot_password"))

        finally:
            if cursor:
                cursor.close()

            if conn and conn.is_connected():
                conn.close()

    return render_template("forgot_password.html")


# Reset Password
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT reset_id, user_id
            FROM password_resets
            WHERE token_hash = %s
              AND used_at IS NULL
              AND expires_at > UTC_TIMESTAMP()
            """,
            (token_hash,)
        )

        reset = cursor.fetchone()

        if not reset:
            flash("This reset link is invalid or has expired.")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if len(password) < 8:
                flash("Password must be at least 8 characters.")
                return render_template("reset_password.html", token=token)

            if password != confirm_password:
                flash("Passwords do not match.")
                return render_template("reset_password.html", token=token)

            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE user_id = %s
                """,
                (generate_password_hash(password), reset["user_id"])
            )

            cursor.execute(
                """
                UPDATE password_resets
                SET used_at = UTC_TIMESTAMP()
                WHERE user_id = %s AND used_at IS NULL
                """,
                (reset["user_id"],)
            )

            conn.commit()

            flash("Password reset successfully. Please sign in.")
            return redirect(url_for("login"))

        return render_template("reset_password.html", token=token)

    except mysql.connector.Error:
        if conn and conn.is_connected():
            conn.rollback()

        app.logger.exception("Password-reset database error")
        flash("Unable to reset your password right now.")
        return redirect(url_for("forgot_password"))

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


# Typing History
@app.route("/history")
def history():
    if "user_id" not in session:
        flash("Please sign in to view your typing history.", "info")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                test_id,
                wpm,
                accuracy,
                duration_seconds,
                completed_at
            FROM typing_history
            WHERE user_id = %s
            ORDER BY completed_at DESC
            """,
            (session["user_id"],)
        )

        tests = cursor.fetchall()

        return render_template("history.html", tests=tests)

    except mysql.connector.Error:
        app.logger.exception("Unable to load typing history")
        flash("Unable to load your typing history.", "error")
        return redirect(url_for("index"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# Typing Test
@app.route("/typing")
def typing():
    difficulty = request.args.get("difficulty", "hard").lower()
    duration = request.args.get("duration", "60")

    if difficulty not in ["easy", "medium", "hard"]:
        difficulty = "hard"

    if duration not in ["30", "60", "120", "300"]:
        duration = "60"

    selected_difficulty = difficulty.capitalize()

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT paragraph_id, paragraph_text
            FROM test_paragraphs
            WHERE difficulty = %s
            ORDER BY RAND()
            LIMIT 1
            """,
            (selected_difficulty,)
        )

        result = cursor.fetchone()

        if not result:
            flash("No paragraphs available for this difficulty.")
            return redirect(url_for("index"))

        paragraph = result["paragraph_text"]

        return render_template(
            "typing.html",
            difficulty=difficulty,
            duration=duration,
            paragraph=paragraph,
            paragraph_id=result["paragraph_id"]
        )

    except mysql.connector.Error:
        app.logger.exception("Unable to retrieve typing paragraph")
        flash("Unable to load the typing paragraph.")
        return redirect(url_for("index"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# Save Typing Result
@app.route("/save-result", methods=["POST"])
def save_result():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please sign in to save your results."
        }), 401

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid result data."
        }), 400

    connection = None
    cursor = None

    try:
        wpm = int(data.get("wpm", 0))
        accuracy = float(data.get("accuracy", 0))
        duration = int(data.get("duration_seconds", 0))
        paragraph_id = int(data.get("paragraph_id", 0))

        if wpm < 0 or not 0 <= accuracy <= 100:
            raise ValueError("Invalid score.")

        if duration not in (30, 60, 120, 300):
            raise ValueError("Invalid duration.")

        if paragraph_id <= 0:
            raise ValueError("Invalid paragraph ID.")

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO typing_history
                (user_id, paragraph_id, wpm, accuracy,
                 duration_seconds, completed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                session["user_id"],
                paragraph_id,
                wpm,
                accuracy,
                duration
            )
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Typing result saved successfully!"
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except mysql.connector.Error:
        app.logger.exception("Failed to save typing result")

        return jsonify({
            "success": False,
            "message": "Unable to save your result."
        }), 500

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(debug=True)
