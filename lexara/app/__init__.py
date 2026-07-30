"""Lexara — a collaborative AI workspace for legal teams."""
import logging

from flask import Flask, jsonify, send_from_directory

from . import config, db, llm

log = logging.getLogger("lexara")


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(config.BASE_DIR / "static"),
        static_url_path="/static",
    )
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
    app.json.sort_keys = False

    db.init()

    from .routes import assistant, documents, playbooks, review, workspaces

    app.register_blueprint(workspaces.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(review.bp)
    app.register_blueprint(assistant.bp)
    app.register_blueprint(playbooks.bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "model": config.MODEL,
                "llm_configured": llm.available(),
            }
        )

    @app.errorhandler(413)
    def too_large(_):
        limit = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        return jsonify({"error": f"File exceeds the {limit} MB upload limit."}), 413

    @app.errorhandler(llm.NotConfigured)
    def llm_missing(exc):
        return jsonify({"error": str(exc), "code": "llm_not_configured"}), 503

    @app.errorhandler(llm.LLMError)
    def llm_failed(exc):
        log.exception("model call failed")
        return jsonify({"error": f"Model call failed: {exc}"}), 502

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Not found"}), 404

    return app
