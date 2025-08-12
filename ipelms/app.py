from pathlib import Path
from flask import Flask, render_template, jsonify

def create_app():
    app = Flask(__name__)

    app.config.update(
        SECRET_KEY="dev",
        MAX_CONTENT_LENGHT=10 * 1024 * 1024, # 10 MB (será usado em uploads)
    )

    app.jinja_env.globals["SITE_NAME"] = "IpêLMS"

    @app.get("/")
    def index():
        return render_template("index.html")
    
    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", app="ipelms", version="0.1.0")
    
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)