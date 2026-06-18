import os
import sqlite3

from functools import wraps

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-secret-key",
)

DATABASE = "users.db"

LOGIN_USERNAME = "admin"
LOGIN_PASSWORD_HASH = generate_password_hash("pass123")


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection

def init_db():
    connection = get_db_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT '未着手',
            priority TEXT NOT NULL DEFAULT '中',
            assignee_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assignee_id) REFERENCES users(id)
        )
        """
    )

    connection.commit()
    connection.close()

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        username_is_correct = username == LOGIN_USERNAME
        password_is_correct = check_password_hash(
            LOGIN_PASSWORD_HASH,
            password,
        )

        if username_is_correct and password_is_correct:
            session.clear()
            session["username"] = username

            return redirect(url_for("task_list"))

        error = "ユーザー名またはパスワードが違います。"

    return render_template("login.html", error=error)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return redirect(url_for("login"))

@app.route("/tasks/create", methods=["GET", "POST"])
@login_required
def task_create():
    connection = get_db_connection()

    users = connection.execute(
        """
        SELECT id, name
        FROM users
        ORDER BY name
        """
    ).fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "未着手")
        priority = request.form.get("priority", "中")
        assignee_id = request.form.get("assignee_id")

        if not title:
            connection.close()

            return render_template(
                "task_create.html",
                users=users,
                error="タイトルを入力してください。",
            )

        if not assignee_id:
            assignee_id = None

        connection.execute(
            """
            INSERT INTO tasks (
                title,
                description,
                status,
                priority,
                assignee_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                status,
                priority,
                assignee_id,
            ),
        )

        connection.commit()
        connection.close()

        return redirect(url_for("task_list"))

    connection.close()

    return render_template(
        "task_create.html",
        users=users,
    )

@app.route("/tasks")
@login_required
def task_list():
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    keyword = request.args.get("keyword", "").strip()
    assignee_id = request.args.get("assignee_id", "").strip()

    sql = """
        SELECT
            tasks.id,
            tasks.title,
            tasks.description,
            tasks.status,
            tasks.priority,
            tasks.created_at,
            users.name AS assignee_name
        FROM tasks
        LEFT JOIN users
            ON tasks.assignee_id = users.id
        WHERE 1 = 1
    """

    parameters = []

    if status:
        sql += " AND tasks.status = ?"
        parameters.append(status)

    if priority:
        sql += " AND tasks.priority = ?"
        parameters.append(priority)

    if keyword:
        sql += """
            AND (
                tasks.title LIKE ?
                OR tasks.description LIKE ?
            )
        """

        like_keyword = f"%{keyword}%"

        parameters.extend([
            like_keyword,
            like_keyword,
        ])

    if assignee_id:
        sql += " AND tasks.assignee_id = ?"
        parameters.append(assignee_id)

    sql += " ORDER BY tasks.id DESC"

    connection = get_db_connection()

    tasks = connection.execute(
        sql,
        parameters,
    ).fetchall()

    users = connection.execute(
        """
        SELECT id, name
        FROM users
        ORDER BY name
        """
    ).fetchall()

    connection.close()

    return render_template(
        "task_list.html",
        tasks=tasks,
        users=users,
        selected_status=status,
        selected_priority=priority,
        selected_keyword=keyword,
        selected_assignee_id=assignee_id,
    )

@app.route("/")
@login_required
def index():
    return redirect(url_for("task_list"))
    """
    ユーザー一覧表示
    """
    connection = get_db_connection()

    users = connection.execute(
        "SELECT id, name, email FROM users ORDER BY id"
    ).fetchall()

    connection.close()

    return render_template("index.html", users=users)


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """
    ユーザー登録
    """
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()

        if not name or not email:
            return render_template(
                "create.html",
                error="名前とメールアドレスを入力してください。",
            )

        connection = get_db_connection()

        connection.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            (name, email),
        )

        connection.commit()
        connection.close()

        return redirect(url_for("index"))

    return render_template("create.html")


@app.route("/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
def edit(user_id):
    """
    ユーザー編集
    """
    connection = get_db_connection()

    user = connection.execute(
        "SELECT id, name, email FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if user is None:
        connection.close()
        return "ユーザーが見つかりません。", 404

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()

        if not name or not email:
            connection.close()

            return render_template(
                "edit.html",
                user=user,
                error="名前とメールアドレスを入力してください。",
            )

        connection.execute(
            """
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
            """,
            (name, email, user_id),
        )

        connection.commit()
        connection.close()

        return redirect(url_for("index"))

    connection.close()

    return render_template("edit.html", user=user)


@app.route("/delete/<int:user_id>", methods=["POST"])
@login_required
def delete(user_id):
    """
    ユーザー削除
    """
    connection = get_db_connection()

    connection.execute(
        "DELETE FROM users WHERE id = ?",
        (user_id,),
    )

    connection.commit()
    connection.close()

    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)